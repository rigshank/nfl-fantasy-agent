"""Real league/statistical analysis plus evidence-aware waiver interpretation."""
from .analysis import owned
from .integrations.gemini import Gemini
from .integrations.nflverse import NFLVerse
from .integrations.research import ProviderUnavailable, Research
from .models import utcnow
from .waivers import WaiverEngine


class WaiverService:
    def __init__(self, config, store, league_service, data_client=None):
        self.config, self.store, self.league_service = config, store, league_service
        self.data_client = data_client or NFLVerse(config, store)

    def analyze(self, fresh, roster_id, protected=None, strategy="balanced", refresh_stats=False, end_week=17,data=None,evaluations=None):
        data = data if data is not None else self.data_client.load(int(fresh.season), dynasty=fresh.league_type == "dynasty",
                                     force=refresh_stats, scoring_rules=fresh.scoring)
        return WaiverEngine(fresh, data, self.config, roster_id, protected, strategy,
                            end_week=max(end_week, fresh.week + 1),evaluations=evaluations).find()

    def find(self, snapshot, roster_id, protected=None, strategy="balanced", refresh_stats=False, end_week=17):
        fresh = self.league_service.load(snapshot.league_id, force=True)
        return fresh, self.analyze(fresh, roster_id, protected, strategy, refresh_stats, end_week)

    def explain(self, snapshot, run, player_id, question="", research=True, history=None):
        fresh = self.league_service.load(snapshot.league_id, force=True)
        if player_id not in run.evaluations or player_id not in fresh.players:
            raise ValueError("This player no longer has a valid evaluation; refresh waiver analysis.")
        current_ownership = {p: r.roster_id for r in fresh.rosters for p in owned(r)}
        old_ownership = {p: r.roster_id for r in snapshot.rosters for p in owned(r)}
        if current_ownership != old_ownership or fresh.scoring != snapshot.scoring or fresh.week != snapshot.week:
            raise ValueError("League ownership or scoring changed. Analyze Waivers again before using this recommendation.")
        if any((utcnow() - source.retrieved_at).total_seconds() > max(86400, self.config.stats_cache_seconds)
               for source in run.sources[:2]):
            raise ValueError("Statistical evidence has expired. Refresh waiver statistics before requesting analysis.")
        pickup = next((p for p in run.pickups if p.player_id == player_id), None)
        breakout = next((b for b in run.breakouts if b.player_id == player_id), None)
        if pickup and (player_id in current_ownership or (pickup.drop_id and current_ownership.get(pickup.drop_id) != run.roster_id)):
            raise ValueError("Pickup/drop ownership is no longer valid; refresh the waiver analysis.")
        ids = [player_id] + ([pickup.drop_id] if pickup and pickup.drop_id else [])
        context = {"league_id": fresh.league_id, "format": fresh.league_type, "my_roster_id": run.roster_id,
            "scoring": fresh.scoring, "roster_slots": fresh.roster_positions, "ownership_refreshed_at": fresh.refreshed_at.isoformat(),
            "statistical_window": [run.start_week, run.end_week], "strategy": run.strategy,
            "protected_players": run.protected, "calculated_waiver": pickup.model_dump(mode="json") if pickup else None,
            "breakout_evidence": breakout.model_dump(mode="json") if breakout else None,
            "players": {p: {"name": fresh.players[p].name, "owner_roster_id": current_ownership.get(p),
                             "injury_metadata": fresh.players[p].injury_status, "evaluation": run.evaluations[p].model_dump(mode="json")} for p in ids},
            "sources": [s.model_dump(mode="json") for s in run.sources], "limitations": run.warnings}
        analyst = Gemini(self.config, self.store)
        analyst.check_model()
        bundle = None
        if research:
            player = fresh.players[player_id]
            try:
                bundle = Research(self.config, self.store).search(
                    f'"{player.name}" {player.team or ""} NFL {fresh.season} injury usage depth chart role')
            except ProviderUnavailable as exc:
                context["limitations"] = context["limitations"] + [str(exc)]
        answer = analyst.answer(context, question or "Evaluate this pickup/drop or emerging player for my actual team. Explain opportunity, current reports, dynasty opportunity cost and uncertainty. State when more evidence is needed.", history or [], bundle)
        return answer, bundle
