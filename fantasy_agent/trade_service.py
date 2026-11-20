"""Refresh league -> cached statistical evidence -> deterministic trade engine."""
from .integrations.nflverse import NFLVerse
from .integrations.research import Research
from .integrations.gemini import Gemini
from .models import ResearchBundle
from .models import utcnow
from .storage import BudgetExceeded
from .integrations.research import ProviderUnavailable
from .trades import TradeEngine, validate_ownership
from .service import analysis_fingerprint


class TradeService:
    def __init__(self, config, store, league_service, data_client=None):
        self.config, self.store, self.league_service = config, store, league_service
        self.data_client = data_client or NFLVerse(config, store)

    def find(self, snapshot, roster_id, options, start_week=None, end_week=17, refresh_stats=False):
        fresh = self.league_service.load(snapshot.league_id, force=True)
        run=self.analyze(fresh,roster_id,options,start_week,end_week,refresh_stats)
        if (utcnow()-fresh.refreshed_at).total_seconds()>self.config.league_cache_seconds:
            verified=self.league_service.load(fresh.league_id,force=True)
            if analysis_fingerprint(verified)!=analysis_fingerprint(fresh):
                raise ValueError("League inputs changed during the long trade search. Recompute before making an offer.")
            fresh=verified
            run.snapshot_at=verified.refreshed_at
        return fresh,run

    def analyze(self,fresh,roster_id,options,start_week=None,end_week=17,refresh_stats=False,data=None,evaluations=None):
        data = data if data is not None else self.data_client.load(int(fresh.season), dynasty=fresh.league_type == "dynasty", force=refresh_stats, scoring_rules=fresh.scoring)
        engine = TradeEngine(fresh, data, self.config, start_week, max(end_week,fresh.week+1),evaluations)
        return engine.discover(roster_id, options)

    @staticmethod
    def explanation_context(snapshot, run, trade):
        validate_ownership(snapshot, trade.my_roster_id, trade.opponent_id, trade.send, trade.receive)
        ids = trade.send + trade.receive + trade.my_drops + trade.opponent_drops
        return {"league_id": snapshot.league_id, "format": snapshot.league_type,
                "scoring": snapshot.scoring, "slots": snapshot.roster_positions,
                "as_of": run.snapshot_at.isoformat(), "forecast_weeks": [run.start_week, run.end_week],
                "calculated_trade": trade.model_dump(mode="json"),
                "players": {p: {"name": snapshot.players[p].name, "catalog_injury": snapshot.players[p].injury_status,
                                "evaluation": run.evaluations[p].model_dump(mode="json")} for p in ids},
                "team_needs": [{"team": t.manager, "roster_id": t.roster_id, "needs": t.needs,
                                "strengths": t.strengths, "coverage": t.coverage} for t in run.teams
                               if t.roster_id in {trade.my_roster_id, trade.opponent_id}],
                "sources": [s.model_dump(mode="json") for s in run.sources],
                "limitations": run.warnings}

    def explain(self, snapshot, run, trade, question, history=None, web=False):
        if (utcnow() - run.snapshot_at).total_seconds() > self.config.league_cache_seconds:
            raise ValueError("Trade calculations are stale. Find Best Trades again before an explanation.")
        # Revalidate ownership and scoring immediately before any explanation.
        fresh = self.league_service.load(snapshot.league_id, force=True)
        validate_ownership(fresh, trade.my_roster_id, trade.opponent_id, trade.send, trade.receive)
        def roster_fingerprint(s):
            return {r.roster_id: (sorted(r.players), sorted(r.reserve), sorted(r.taxi)) for r in s.rosters}
        relevant = trade.send + trade.receive
        status_changed = any(p not in fresh.players or (fresh.players[p].injury_status, fresh.players[p].active) !=
                             (snapshot.players[p].injury_status, snapshot.players[p].active) for p in relevant)
        if fresh.scoring != snapshot.scoring or fresh.roster_positions != snapshot.roster_positions or fresh.settings != snapshot.settings or fresh.league_type != snapshot.league_type or roster_fingerprint(fresh) != roster_fingerprint(snapshot) or status_changed:
            raise ValueError("League rosters/rules changed. Find Best Trades again before requesting an explanation.")
        analyst = Gemini(self.config, self.store)
        analyst.check_model()
        bundle = None
        research_error = None
        if web:
            names = [snapshot.players[p].name for p in trade.send + trade.receive]
            query = " OR ".join('"' + name + '"' for name in names)
            # One query for the selected package, never one search per player.
            try:
                bundle = Research(self.config, self.store).search(f"{query} NFL {snapshot.season} injury usage depth chart")
            except (ProviderUnavailable, BudgetExceeded) as exc:
                research_error = str(exc)
        context = self.explanation_context(fresh, run, trade)
        if research_error:
            context["limitations"] = context["limitations"] + ["Web research failed: " + research_error]
        answer = analyst.answer(context, question or "Explain this trade for both managers, including risks, evidence and uncertainty.", history or [], bundle)
        if research_error:
            answer = "**Web research unavailable; explanation uses statistical evidence only.**\n\n" + answer
        return answer, bundle
