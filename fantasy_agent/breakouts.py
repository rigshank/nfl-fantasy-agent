"""Independent opportunity analysis; a missing own starter cannot hide free-player trends."""
from datetime import datetime
from pydantic import BaseModel
from .evaluation import evaluate_players
from .models import utcnow
from .integrations.nflverse import NFLVerse
from .integrations.sleeper import DataUnavailable
from .trade_models import Evaluation,SourceInfo
from .waivers import BreakoutSignal,breakout_signals


class BreakoutRun(BaseModel):
    league_id: str
    snapshot_at: datetime
    week: int
    evaluations: dict[str,Evaluation]
    signals: list[BreakoutSignal]
    sources: list[SourceInfo]
    warnings: list[str]


class BreakoutService:
    def __init__(self,config,store,league_service,data_client=None):
        self.config,self.store,self.league_service=config,store,league_service
        self.data_client=data_client or NFLVerse(config,store)

    def analyze(self,fresh,refresh_stats=False):
        if any("Archived/future" in w for w in fresh.warnings):
            raise DataUnavailable("Select a current-season league for current breakout analysis.")
        data=self.data_client.load(int(fresh.season),scoring_rules=fresh.scoring,force=refresh_stats)
        values,warnings=evaluate_players(fresh,data,fresh.week,18,self.config.dynasty_max_age_days)
        return BreakoutRun(league_id=fresh.league_id,snapshot_at=fresh.refreshed_at,week=fresh.week,
            evaluations=values,signals=breakout_signals(values),sources=data.sources,warnings=warnings)

    def find(self,snapshot,refresh_stats=False):
        fresh=self.league_service.load(snapshot.league_id,force=True)
        return fresh,self.analyze(fresh,refresh_stats)
