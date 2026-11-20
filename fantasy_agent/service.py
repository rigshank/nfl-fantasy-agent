import re
from concurrent.futures import ThreadPoolExecutor
from .analysis import depth, free_players, owned, roster_warnings
from .config import Config
from .models import Player, Snapshot
from .normalization import league_type, player_from_raw, roster_from_raw
from .integrations.sleeper import DataUnavailable, Sleeper
from .storage import Store


def analysis_fingerprint(s):
    """Inputs that invalidate decisions; fluctuating live points are timestamped,
    while owner, starter, eligibility and rule changes invalidate the calculation.
    """
    return (s.league_id,s.season,s.week,s.league_type,s.league_status,s.scoring,s.roster_positions,s.settings,
        [(r.roster_id,r.owner_id,sorted(r.co_owners),r.manager,sorted(owned(r)),r.starters,sorted(r.reserve),sorted(r.taxi)) for r in sorted(s.rosters,key=lambda r:r.roster_id)],
        [(m.get("roster_id"),m.get("matchup_id"),m.get("starters")) for m in sorted(s.matchups,key=lambda m:m.get("roster_id",0))],
        [(pid,p.team,p.positions,p.injury_status,p.status,p.active,p.known) for pid,p in sorted(s.players.items())])


class LeagueService:
    def __init__(self, config: Config, store: Store, sleeper: Sleeper):
        self.config, self.store, self.sleeper = config, store, sleeper

    def load(self, league_id: str, force=False) -> Snapshot:
        if not re.fullmatch(r"\d{5,30}", league_id):
            raise ValueError("Enter a numeric Sleeper league ID (5–30 digits).")
        key = f"snapshot:{league_id}"
        cached = self.store.get(key)
        if cached and not force:
            return Snapshot.model_validate(cached[0])
        base = f"/league/{league_id}"
        league = self.sleeper.get(base, self.config.league_cache_seconds, force)[0]
        if not isinstance(league,dict) or not {"sport","season","name","roster_positions"} <= league.keys() or not isinstance(league.get("roster_positions"),list):
            raise DataUnavailable("Sleeper league response is incomplete. Verify the league ID and retry.")
        if league.get("sport") != "nfl":
            raise DataUnavailable("This app supports NFL leagues only.")
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs={k:pool.submit(self.sleeper.get,p,force=force) for k,p in
                  {"users":base+"/users","rosters":base+"/rosters","state":"/state/nfl"}.items()}
            users,raw_rosters,state=(jobs[k].result()[0] for k in ("users","rosters","state"))
        if not isinstance(users,list) or not isinstance(raw_rosters,list) or not isinstance(state,dict):
            raise DataUnavailable("Sleeper roster/user/NFL-state response has an unexpected format. Retry the refresh.")
        if any(not isinstance(u,dict) or "user_id" not in u for u in users) or any(not isinstance(r,dict) or "roster_id" not in r for r in raw_rosters) or not state.get("season"):
            raise DataUnavailable("Sleeper omitted required user, roster or current NFL season fields. Retry the refresh.")
        if not raw_rosters:
            raise DataUnavailable("This league has no rosters yet.")
        catalog, catalog_at = self.sleeper.catalog()
        players = {str(pid): player_from_raw(pid, p) for pid, p in catalog.items()}
        rosters = [roster_from_raw(r, {u["user_id"]: u for u in users}) for r in raw_rosters]
        warnings = []
        for roster in rosters:
            for pid in owned(roster) | (set(roster.starters) - {"0"}):
                if pid not in players:
                    players[pid] = Player(player_id=pid, name=f"Unknown player ({pid})", known=False)
                    warnings.append(f"Unresolved player ID {pid}; no name match was guessed.")
            warnings.extend(f"{roster.manager}: {w}" for w in roster_warnings(roster, league["roster_positions"], players))
        seen = set()
        for roster in rosters:
            duplicate = seen.intersection(owned(roster))
            if duplicate:
                warnings.append(f"Ownership conflict across teams for IDs {sorted(duplicate)}; verify Sleeper before advising.")
            seen.update(owned(roster))
        same_season = str(state.get("season")) == str(league["season"])
        week = int(state.get("display_week") or state.get("week") or 1) if same_season else 1
        week = max(1, min(week, 18))
        if not same_season:
            warnings.append("Archived/future league: showing week 1, not current NFL matchups.")
        extras = {}
        paths={"matchups":f"/matchups/{week}","transactions":f"/transactions/{week}","traded_picks":"/traded_picks","drafts":"/drafts"}
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs={k:pool.submit(self.sleeper.get,base+p,force=force) for k,p in paths.items()}
            for field,job in jobs.items():
                try:
                    value=job.result()[0]
                    if not isinstance(value,list):raise DataUnavailable("Unexpected response format")
                    extras[field]=value
                except (DataUnavailable,RuntimeError) as exc:
                    warnings.append(f"{field} unavailable on this refresh; omitted, not confirmed empty. {exc}")
        settings = league.get("settings") or {}
        snapshot = Snapshot(league_id=league_id, name=league["name"], season=str(league["season"]),
                            week=week, league_type=league_type(settings),
                            league_status=league.get("status"),
                            roster_positions=league["roster_positions"], settings=settings,
                            scoring=league.get("scoring_settings") or {}, metadata=league.get("metadata") or {},
                            rosters=rosters, players=players, catalog_at=catalog_at,
                            warnings=warnings, **extras)
        self.store.put(key, snapshot.model_dump(mode="json"), self.config.league_cache_seconds)
        return snapshot


def compact_context(snapshot: Snapshot, roster_id: int, question="") -> dict:
    roster_ids = set().union(*(owned(r) for r in snapshot.rosters))
    free = free_players(snapshot)
    terms = question.casefold()
    relevant_free = [p for p in free if p.name.casefold() in terms]
    player_ids = roster_ids | {p.player_id for p in relevant_free}
    return {"league_id": snapshot.league_id, "name": snapshot.name, "season": snapshot.season,
            "week": snapshot.week, "format": snapshot.league_type,
            "my_roster_id": roster_id, "as_of": snapshot.refreshed_at.isoformat(),
            "catalog_as_of": snapshot.catalog_at.isoformat(),
            "slots": snapshot.roster_positions, "scoring": snapshot.scoring,
            "settings": snapshot.settings,
            "teams": [{"id": r.roster_id, "name": r.manager, "players": sorted(owned(r)),
                       "starters": r.starters, "ir": r.reserve, "taxi": r.taxi,
                       "record": r.settings, "depth_counts": depth(snapshot, r)} for r in snapshot.rosters],
            "players": {pid: {"name": snapshot.players[pid].name, "pos": snapshot.players[pid].positions,
                             "team": snapshot.players[pid].team, "catalog_injury": snapshot.players[pid].injury_status}
                        for pid in sorted(player_ids)},
            "free_agent_pool_size": len(free), "named_free_agents_included": len(relevant_free),
            "matchups": snapshot.matchups,
            "recent_transactions": snapshot.transactions, "traded_picks": snapshot.traded_picks,
            "warnings": snapshot.warnings,
            "limitations": ["No player statistics, projections, value model, schedule or lineup optimizer loaded.",
                            "Free agent metadata in this base context includes exact full names mentioned in the question; statistical evidence may be attached separately.",
                            "Transactions cover displayed week only; moved picks are not a complete pick inventory."]}
