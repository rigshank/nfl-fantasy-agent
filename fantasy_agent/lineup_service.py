"""Shared current/future weekly lineup calculations and conservative game locks."""
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import statistics
import numpy as np
from pydantic import BaseModel, Field

from .analysis import owned, FLEX_POSITIONS, roster_warnings
from .evaluation import evaluate_players, id_index, team_code, UNAVAILABLE
from .integrations.nflverse import NFLVerse, SCHEDULE_URL
from .integrations.sleeper import DataUnavailable
from .lineup import LineupOptimizer
from .models import utcnow
from .special_scoring import score_special
from .trade_models import SourceInfo

TEAM_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_{season}.csv"


class LineupSlot(BaseModel):
    index: int
    slot: str
    current_id: str | None
    recommended_id: str | None
    current_estimate: float | None
    estimate: float | None
    objective: float | None
    opponent: str | None = None
    kickoff: str | None = None
    locked: bool = False
    reason: str


class LineupReport(BaseModel):
    roster_id: int
    week: int
    strategy: str
    snapshot_at: str
    calculated_at: str
    slots: list[LineupSlot]
    current_total: float | None
    expected_total: float | None
    expected_gain: float | None
    complete: bool
    warnings: list[str]
    sources: list[SourceInfo]
    evidence: dict = Field(default_factory=dict)
    excluded_players: list[str] = Field(default_factory=list)


def kickoff(row):
    """nflverse gametime is US Eastern; unknown/TBD is never treated as unlocked."""
    try:
        return datetime.fromisoformat(row["gameday"] + "T" + row["gametime"]).replace(tzinfo=ZoneInfo("America/New_York"))
    except (KeyError, TypeError, ValueError):
        return None


class LineupService:
    def __init__(self, config, store, league_service=None, data_client=None):
        self.config, self.store, self.league_service = config, store, league_service
        self.data_client = data_client or NFLVerse(config, store)

    def find(self, snapshot, roster_id, week=None, strategy="expected", refresh_stats=False,excluded=None):
        fresh = self.league_service.load(snapshot.league_id, force=True)
        data = self.data_client.load(int(fresh.season), scoring_rules=fresh.scoring, force=refresh_stats)
        # Kickoffs must not use the six-hour statistical cache.
        data.schedule, source = self.data_client.csv("nflverse live schedule", SCHEDULE_URL,
                {"season", "week", "home_team", "away_team", "gameday"}, ttl=300)
        data.sources.append(source)
        return fresh, self.analyze(fresh, data, roster_id, week, strategy,excluded=excluded)

    def analyze(self, snapshot, data, roster_id, week=None, strategy="expected", now=None,evaluations=None,excluded=None):
        now = now or utcnow()
        week = snapshot.week if week is None else int(week)
        if not snapshot.week <= week <= 18 or strategy not in {"expected", "upside", "floor"}:
            raise ValueError("Choose current/future regular-season week and expected, upside or floor strategy.")
        if any("Archived/future" in w for w in snapshot.warnings) or snapshot.league_status != "in_season":
            raise DataUnavailable("Live lineup recommendations require the current in-season league.")
        if (now - snapshot.refreshed_at).total_seconds() > self.config.league_cache_seconds:
            raise DataUnavailable("League roster is stale. Refresh before optimizing.")
        roster = next((r for r in snapshot.rosters if r.roster_id == roster_id),None)
        if roster is None:
            raise ValueError("Selected team is absent from the refreshed league. Choose your team again.")
        if (now - snapshot.catalog_at).total_seconds() > 86400:
            raise DataUnavailable("Player catalog is stale. Refresh before optimizing.")
        issues = roster_warnings(roster, snapshot.roster_positions, snapshot.players)
        ownership = Counter(p for r in snapshot.rosters for p in owned(r))
        if issues or any(ownership[p] != 1 for p in owned(roster)):
            raise DataUnavailable("Invalid roster/ownership: " + "; ".join(issues or ["conflicting ownership"]))
        values, warnings = evaluations if evaluations is not None else evaluate_players(snapshot, data, week, week, self.config.dynasty_max_age_days)
        warnings = [w for w in warnings if not w.startswith("K/DEF/IDP held")]
        active = owned(roster) - set(roster.reserve + roster.taxi)
        excluded=set(excluded or [])
        if not excluded<=owned(roster):raise ValueError("Lineup exclusions must belong to your selected team.")
        games, team_weeks = {}, defaultdict(set)
        for game in data.schedule:
            if str(game.get("season")) != snapshot.season or game.get("game_type", "REG") != "REG":
                continue
            for team in (game["home_team"], game["away_team"]):
                team_weeks[team_code(team)].add(int(game["week"]))
                if int(game["week"]) == week:
                    if team_code(team) in games:
                        raise DataUnavailable("Duplicate team/week schedule rows.")
                    games[team_code(team)] = game
        forecasts, objectives, evidence = {}, {}, {}
        for pid in active:
            p, v = snapshot.players[pid], values.get(pid)
            game = games.get(team_code(p.team or (pid if "DEF" in p.positions else None)))
            if v:
                evidence[pid] = v.model_dump(mode="json")
                if v.available and game:
                    forecasts[pid] = v.weekly[week]
                    # Strategy shifts are explicit historical variability heuristics,
                    # not probabilistic forecasts or fabricated expert projections.
                    delta = max(0, v.upside - v.projected_ppg) * .5 if strategy == "upside" else -max(0, v.projected_ppg - v.floor) * .5 if strategy == "floor" else 0
                    objectives[pid] = forecasts[pid] + delta
        special = [p for p in active if not {"QB", "RB", "WR", "TE"}.intersection(snapshot.players[p].positions)]
        if special:
            self._special(snapshot, data, special, week, strategy, forecasts, objectives, evidence, warnings)
        slots = [s for s in snapshot.roster_positions if s not in {"BN", "IR", "TAXI"}]
        saved = list(roster.starters)
        if week == snapshot.week:
            matchup = next((m for m in snapshot.matchups if m.get("roster_id") == roster_id), None)
            if matchup and "starters" in matchup:
                saved = matchup["starters"]
        if len(saved) != len(slots) or len([p for p in saved if p != "0"]) != len(set(saved) - {"0"}):
            raise DataUnavailable("Current-week starter slots are missing or duplicated; refresh Sleeper.")
        current = [p if p != "0" else None for p in saved]
        if any(p and (p not in active or not set(snapshot.players[p].positions).intersection(FLEX_POSITIONS.get(s, {s}))) for s,p in zip(slots,current)):
            raise DataUnavailable("Current-week starters fail ownership/slot eligibility checks.")
        locked, unknown = {}, set()
        if week == snapshot.week:
            for pid in active:
                p = snapshot.players[pid]
                team = team_code(p.team or (pid if "DEF" in p.positions else None))
                game = games.get(team)
                start = kickoff(game) if game else None
                if game and (start is None or start <= now):
                    unknown.add(pid)
                elif not game and len(team_weeks[team]) != 17:
                    unknown.add(pid)
            for i, pid in enumerate(current):
                if pid in unknown:
                    locked[i] = pid
            if unknown:
                warnings.append("Started games and unknown kickoff/status are conservatively locked; locked bench players cannot enter. Postponements/late inactives require checking Sleeper before submitting.")
        # Unsupported/unmeasured slots stay unchanged with unknown points, never
        # fabricated scores. Supported but injured/bye starters can be replaced.
        for i,(slot,pid) in enumerate(zip(slots,current)):
            candidates = [p for p in active-excluded if p in forecasts and set(snapshot.players[p].positions).intersection(FLEX_POSITIONS.get(slot,{slot}))]
            if not candidates and pid and pid not in evidence:
                locked[i] = pid
        usable = set(objectives) - unknown - excluded
        solved = LineupOptimizer(snapshot.players, slots, all_positions=True).solve(usable, objectives, locked, fill=True)
        rows = []
        for i, (slot, pid, _) in enumerate(solved.assignments):
            previous = current[i]
            p = snapshot.players[pid] if pid else None
            team = team_code(p.team or (pid if "DEF" in p.positions else None)) if p else None
            game = games.get(team) if pid else None
            start = kickoff(game) if game else None
            opponent = None
            if game and pid:
                opponent = team_code(game["away_team"]) if team == team_code(game["home_team"]) else team_code(game["home_team"])
            reason = ("Game started or kickoff unverified; keep saved slot." if pid in unknown else "Missing/unsupported scoring evidence; saved slot retained for manual review.") if i in locked else "Exact legal assignment maximizes the selected strategy using league-scored statistical estimates."
            if pid and snapshot.players[pid].injury_status:
                reason += " Injury designation: " + snapshot.players[pid].injury_status + "; verify current reports."
            if pid != previous:
                reason += " Replaces saved starter; all flex slots and opportunity/matchup evidence were recomputed."
            previous_points = forecasts.get(previous)
            if previous is None:
                previous_points = 0.
            elif previous_points is None:
                old = snapshot.players[previous]
                old_team = team_code(old.team or (previous if "DEF" in old.positions else None))
                if (old_team not in games and len(team_weeks[old_team]) == 17) or str(old.injury_status or "").upper() in UNAVAILABLE:
                    previous_points = 0.
            live_locked = pid in unknown
            rows.append(LineupSlot(index=i, slot=slot, current_id=previous, recommended_id=pid,
                current_estimate=None if previous in unknown else previous_points,
                estimate=None if live_locked else forecasts.get(pid), objective=None if live_locked else objectives.get(pid),
                opponent=opponent, kickoff=start.isoformat() if start else None, locked=i in locked, reason=reason))
        # Totals are only complete when every slot has a supported estimate and
        # no game has started. Live earned points are not mixed with full-game forecasts.
        full = all(r.estimate is not None and r.recommended_id for r in rows)
        before = sum(r.current_estimate for r in rows) if all(r.current_estimate is not None for r in rows) else None
        after = sum(r.estimate for r in rows) if full else None
        warnings.extend(["All numbers are league-scored statistical estimates; no licensed/expert projection feed is available.",
            "Upside/floor objectives add/subtract half the historical quantile gap; expected points remain displayed separately. These are uncalibrated strategy heuristics.",
            "Injury metadata is the daily Sleeper catalog, not live NFL inactive confirmation. Research questionable starters before kickoff."])
        if excluded:warnings.append("Explicit exclusions: "+", ".join(snapshot.players[p].name for p in sorted(excluded))+". Exclusions do not unlock an already-started saved starter or imply a medical diagnosis.")
        return LineupReport(roster_id=roster_id, week=week, strategy=strategy, snapshot_at=snapshot.refreshed_at.isoformat(),
            calculated_at=now.isoformat(), slots=rows, current_total=before, expected_total=after,
            expected_gain=after-before if after is not None and before is not None else None, complete=bool(full),
            warnings=warnings, sources=data.sources, evidence={p:evidence[p] for p in active if p in evidence},excluded_players=sorted(excluded))

    def _special(self, snapshot, data, ids, week, strategy, forecasts, objectives, evidence, warnings):
        gsis = id_index(data.ids, "gsis_id")
        histories = defaultdict(list)
        for row in data.stats:
            if row.get("season_type", "REG") == "REG" and int(row["week"]) < snapshot.week and gsis.get(row["player_id"]) in ids:
                histories[gsis[row["player_id"]]].append(row)
        team_rows = []
        if any("DEF" in snapshot.players[p].positions for p in ids):
            try:
                team_rows, source = self.data_client.csv("nflverse team defense statistics", TEAM_STATS_URL.format(season=snapshot.season), {"season","week","team","opponent_team"})
                data.sources.append(source)
            except DataUnavailable as exc:
                warnings.append(str(exc))
        team_lookup = {(team_code(r["team"]), int(r["week"])):r for r in team_rows if r.get("season_type", "REG") == "REG" and str(r.get("season")) == snapshot.season}
        eligible_rows=[r for r in team_rows if r.get("season_type","REG")=="REG" and str(r.get("season"))==snapshot.season]
        if len(team_lookup)!=len(eligible_rows):
            warnings.append("Duplicate team/week defense records; no defense estimate supplied.")
            team_lookup={}
        for game in data.schedule:
            if str(game.get("season"))!=snapshot.season or game.get("game_type","REG")!="REG":continue
            for side in ("home","away"):
                key=(team_code(game[side+"_team"]),int(game["week"]))
                if key in team_lookup:
                    team_lookup[key]={**team_lookup[key],"points_scored":game.get(side+"_score")}
        for pid in ids:
            p = snapshot.players[pid]
            kind = "DEF" if "DEF" in p.positions else "K" if "K" in p.positions else "IDP"
            rows = [r for (team,w),r in team_lookup.items() if team==team_code(p.team or pid) and w < snapshot.week] if kind=="DEF" else histories[pid]
            rows = sorted(rows, key=lambda r:int(r["week"]))
            if not rows or len({int(r["week"]) for r in rows}) != len(rows):
                warnings.append(p.name+": no unambiguous specialist history; no estimate supplied.")
                continue
            try:
                observed = [score_special(r,snapshot.scoring,kind,team_lookup.get((team_code(r.get("opponent_team")),int(r["week"])))) for r in rows]
            except ValueError as exc:
                warnings.append(p.name+": "+str(exc));continue
            estimate = .65*statistics.mean(observed[-4:])+.35*statistics.mean(observed)
            evidence[pid] = {"observed_weekly":list(zip([int(r["week"]) for r in rows],observed)),"estimate":estimate,
                "method":"65% last-four/35% full-season league-scored mean; specialist matchup adjustment unavailable"}
            game = next((r for r in data.schedule if str(r.get("season"))==snapshot.season and r.get("game_type","REG")=="REG" and int(r["week"])==week and team_code(p.team or pid) in {team_code(r["home_team"]),team_code(r["away_team"])}),None)
            completed=max((int(r["week"]) for r in data.stats if int(r["week"])<snapshot.week),default=0)
            latest=max(int(r["week"]) for r in rows)
            missed_latest=latest<completed and any(int(r["week"])==completed and team_code(p.team or pid) in {team_code(r["home_team"]),team_code(r["away_team"])} for r in data.schedule if str(r.get("season"))==snapshot.season and r.get("game_type","REG")=="REG")
            if p.known and p.active and game and latest>=completed-1 and not missed_latest and str(p.injury_status or "").upper() not in UNAVAILABLE and str(p.status or "").upper() not in UNAVAILABLE:
                forecasts[pid] = estimate
                objectives[pid] = estimate + .5*max(0,float(np.quantile(observed,.8))-estimate) if strategy=="upside" else estimate-.5*max(0,estimate-float(np.quantile(observed,.2))) if strategy=="floor" else estimate
            warnings.append(p.name+": specialist estimate uses observed scoring; matchup/role forecasts are less developed than offensive estimates.")
