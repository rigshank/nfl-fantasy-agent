"""Small official/public CSV releases. No scraping, names-as-IDs, or paid feed."""
import csv
import io
import time
from tempfile import NamedTemporaryFile
from pathlib import Path
import pyarrow.parquet as pq
import httpx
from ..config import Config
from ..storage import Store
from ..trade_models import SourceInfo, TradeData
from .sleeper import DataUnavailable
from ..play_events import PBP_COLUMNS, REQUIRED_COLUMNS, aggregate_plays
from ..scoring import EVENT_FIELDS, STAT_FIELDS
from ..models import utcnow


STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
SNAPS_URL = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.csv"
IDS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
SCHEDULE_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
DYNASTY_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"


class NFLVerse:
    def __init__(self, config: Config, store: Store, client=None):
        self.config, self.store = config, store
        self.client = client or httpx.Client(timeout=45, follow_redirects=True)

    def csv(self, name, url, required, force=False, ttl=None):
        key = "csv:v1:" + url
        cached = self.store.get(key)
        if not cached or force or (ttl and (utcnow() - cached[1]).total_seconds() > ttl):
            for attempt in range(3):
                self.store.record_request("nflverse")
                try:
                    with self.client.stream("GET", url) as response:
                        if response.status_code == 429 or response.status_code >= 500:
                            if attempt < 2:
                                time.sleep(2 ** attempt)
                                continue
                        response.raise_for_status()
                        chunks, size = [], 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 32 * 1024 * 1024:
                                raise DataUnavailable(f"{name} exceeds the compact feed size limit.")
                            chunks.append(chunk)
                        reader = csv.DictReader(io.StringIO(b"".join(chunks).decode("utf-8-sig")))
                        if not required <= set(reader.fieldnames or []):
                            raise DataUnavailable(f"{name} schema changed: missing {sorted(required - set(reader.fieldnames or []))}.")
                        rows = list(reader)
                        if not rows:
                            raise DataUnavailable(f"{name} returned no rows.")
                        self.store.put(key, {"rows": rows, "updated": response.headers.get("last-modified")},
                                       ttl or self.config.stats_cache_seconds)
                        cached = self.store.get(key)
                        break
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    raise DataUnavailable(f"{name} is unreachable; trade analysis stopped.") from None
                except httpx.HTTPStatusError as exc:
                    raise DataUnavailable(f"{name}: HTTP {exc.response.status_code} {exc.response.reason_phrase}. Retry the source refresh after the provider recovers.") from None
                except (UnicodeError, csv.Error) as exc:
                    raise DataUnavailable(f"{name} could not be parsed: {exc}. No substitute statistics were used.") from None
        return cached[0]["rows"], SourceInfo(name=name, url=url, retrieved_at=cached[1],
                                             source_updated_at=cached[0].get("updated"))

    def play_events(self, season, force=False):
        url = PBP_URL.format(season=season)
        key = "pbp-events:v1:" + url
        cached = self.store.get(key)
        if not cached or force:
            temp_path = None
            try:
                self.store.record_request("nflverse")
                with NamedTemporaryFile(suffix=".parquet", dir=self.store.path.parent, delete=False) as file:
                    temp_path = Path(file.name)
                    with self.client.stream("GET", url) as response:
                        response.raise_for_status()
                        size = 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 96 * 1024 * 1024:
                                raise DataUnavailable("Play-by-play exceeds the compact download limit.")
                            file.write(chunk)
                        updated = response.headers.get("last-modified")
                parquet = pq.ParquetFile(temp_path)
                try:
                    columns = set(parquet.schema_arrow.names)
                    if not REQUIRED_COLUMNS <= columns:
                        raise DataUnavailable("Play-by-play scoring schema changed; missing required fields: " + ", ".join(sorted(REQUIRED_COLUMNS - columns)))
                    def rows():
                        for batch in parquet.iter_batches(batch_size=10000, columns=sorted(PBP_COLUMNS & columns)):
                            yield from batch.to_pylist()
                    events, games = aggregate_plays(rows(), season)
                finally:
                    parquet.close()
                self.store.put(key, {"events": events, "games": games, "updated": updated}, self.config.stats_cache_seconds)
                cached = self.store.get(key)
            except (httpx.HTTPError, ValueError, OSError) as exc:
                raise DataUnavailable(f"Play-by-play scoring/usage supplement failed: {exc}. Retry the source refresh; long-TD bonuses cannot be assumed zero.") from None
            finally:
                if temp_path and temp_path.exists():
                    temp_path.unlink()
        return cached[0]["events"], cached[0]["games"], SourceInfo(name="nflverse play-by-play scoring and red-zone usage", url=url,
                retrieved_at=cached[1], source_updated_at=cached[0].get("updated"))

    def load(self, season: int, dynasty=False, force=False, scoring_rules=None) -> TradeData:
        if not 2017 <= season <= 2100:
            raise ValueError("Unsupported season.")
        stats, stat_source = self.csv("nflverse weekly player stats", STATS_URL.format(season=season),
                                      {"player_id", "season", "week", "season_type", "position"}, force)
        ids, id_source = self.csv("DynastyProcess player IDs", IDS_URL, {"gsis_id", "sleeper_id"}, force, 86400)
        data = TradeData(season=season,
                         stats=[r for r in stats if r["season"] == str(season) and r["season_type"] == "REG"],
                         ids=ids, sources=[stat_source, id_source])
        if scoring_rules is not None:
            try:
                data.scoring_events, data.event_games, source = self.play_events(season, force)
                data.sources.append(source)
            except (DataUnavailable, RuntimeError) as exc:
                needed = any(v and STAT_FIELDS.get(k) in EVENT_FIELDS for k, v in scoring_rules.items())
                if needed:
                    raise DataUnavailable(str(exc)) from None
                data.warnings.append(str(exc))
        for field, name, url, columns in [
            ("schedule", "nflverse NFL schedule", SCHEDULE_URL, {"season", "week", "home_team", "away_team", "gameday"}),
            ("snaps", "nflverse PFR snap counts", SNAPS_URL.format(season=season), {"pfr_player_id", "week", "offense_pct"}),
        ]:
            try:
                rows, source = self.csv(name, url, columns, force)
                setattr(data, field, [r for r in rows if r.get("season") == str(season)])
                data.sources.append(source)
            except (DataUnavailable, RuntimeError) as exc:
                data.warnings.append(str(exc))
        if dynasty:
            try:
                data.dynasty, source = self.csv("DynastyProcess community dynasty values", DYNASTY_URL,
                                               {"fp_id", "value_1qb", "value_2qb", "scrape_date"}, force, 86400)
                data.sources.append(source)
            except (DataUnavailable, RuntimeError) as exc:
                data.warnings.append(str(exc))
        if not data.stats:
            raise DataUnavailable("No regular-season statistics for this season; trades cannot be ranked.")
        return data
