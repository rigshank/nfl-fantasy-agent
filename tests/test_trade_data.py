import csv
import io
import httpx
import pytest
from fantasy_agent.integrations.nflverse import NFLVerse, STATS_URL, IDS_URL, SCHEDULE_URL, SNAPS_URL, DYNASTY_URL
from fantasy_agent.integrations.sleeper import DataUnavailable


def csv_response(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return httpx.Response(200, text=out.getvalue(), headers={"last-modified": "Thu, 19 Nov 2026 01:00:00 GMT"})


def test_stat_adapter_uses_documented_sources_and_caches(config, store):
    responses = {
        STATS_URL.format(season=2026): [{"player_id": "gsis-1", "season": 2026, "week": 10, "season_type": "REG", "position": "RB", "carries": 18}],
        IDS_URL: [{"gsis_id": "gsis-1", "sleeper_id": "8155"}],
        SCHEDULE_URL: [{"season": 2026, "week": 12, "home_team": "KC", "away_team": "BUF", "gameday": "2026-11-29"}],
        SNAPS_URL.format(season=2026): [{"season": 2026, "pfr_player_id": "pfr1", "week": 10, "offense_pct": .75}],
        DYNASTY_URL: [{"fp_id": "123", "value_1qb": 4000, "value_2qb": 3500, "scrape_date": "2026-11-19"}],
    }
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return csv_response(responses[str(request.url)])
    adapter = NFLVerse(config, store, httpx.Client(transport=httpx.MockTransport(handler)))
    first = adapter.load(2026, dynasty=True)
    adapter.load(2026, dynasty=True)
    assert len(calls) == 5
    assert len(first.stats) == 1 and len(first.sources) == 5
    assert first.sources[0].source_updated_at
    adapter.load(2026, dynasty=True, force=True)
    assert len(calls) == 10


def test_schema_change_is_not_silently_accepted(config, store):
    adapter = NFLVerse(config, store, httpx.Client(transport=httpx.MockTransport(
        lambda r: csv_response([{"different_id": "1"}]))))
    with pytest.raises(DataUnavailable, match="schema"):
        adapter.load(2026)


def test_csv_rate_limit_retries_bounded_and_records_attempts(config, store, monkeypatch):
    monkeypatch.setattr("fantasy_agent.integrations.nflverse.time.sleep", lambda _: None)
    codes = iter([429, 503, 200])
    def handler(request):
        code = next(codes)
        return csv_response([{"id": "1"}]) if code == 200 else httpx.Response(code)
    adapter = NFLVerse(config, store, httpx.Client(transport=httpx.MockTransport(handler)))
    rows, _ = adapter.csv("test", "https://example.test/stats.csv", {"id"})
    assert rows == [{"id": "1"}]
    assert store.usage()[0]["requests"] == 3
