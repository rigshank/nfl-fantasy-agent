"""Evidence, forecasts and trade calculations have distinct typed contracts."""
from datetime import datetime
from pydantic import BaseModel, Field
from .models import utcnow


class SourceInfo(BaseModel):
    name: str
    url: str
    retrieved_at: datetime
    source_updated_at: str | None = None
    stale: bool = False


class TradeData(BaseModel):
    season: int
    stats: list[dict]
    ids: list[dict]
    snaps: list[dict] = Field(default_factory=list)
    schedule: list[dict] = Field(default_factory=list)
    dynasty: list[dict] = Field(default_factory=list)
    scoring_events: list[dict] = Field(default_factory=list)
    event_games: list[str] = Field(default_factory=list)
    sources: list[SourceInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Evaluation(BaseModel):
    player_id: str
    position: str
    games: int
    last_week: int
    season_ppg: float
    recent_ppg: float
    projected_ppg: float
    floor: float
    upside: float
    consistency_sd: float
    opportunities: float | None = None
    recent_opportunities: float | None = None
    opportunity_trend: float | None = None
    snap_pct: float | None = None
    recent_snaps: float | None = None
    snap_trend: float | None = None
    targets: float | None = None
    carries: float | None = None
    receptions: float | None = None
    red_zone_targets: float | None = None
    red_zone_carries: float | None = None
    goal_line_carries: float | None = None
    td_share: float | None = None
    offensive_environment: float | None = None
    trend: str
    age: float | None = None
    dynasty_value: float | None = None
    dynasty_date: str | None = None
    available: bool = True
    risk: float = 0
    weekly: dict[int, float] = Field(default_factory=dict)
    opponents: dict[int, str] = Field(default_factory=dict)
    schedule_factors: dict[int, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    weekly_observed: list[dict] = Field(default_factory=list)


class Lineup(BaseModel):
    total: float
    assignments: list[tuple[str, str | None, float]]
    missing_slots: int = 0


class TeamReport(BaseModel):
    roster_id: int
    manager: str
    coverage: float
    next_lineup: Lineup
    ros_total: float
    positional_surplus: dict[str, float]
    bench_depth: dict[str, int]
    strengths: list[str]
    needs: list[str]
    injured: list[str]
    expendable: list[str]
    eligible_partner: bool
    warnings: list[str] = Field(default_factory=list)


class TradeOptions(BaseModel):
    structures: list[tuple[int, int]] = Field(default_factory=lambda: [(1, 1), (2, 1), (2, 2), (3, 2)])
    opponent_id: int | None = None
    receive_position: str | None = None
    must_send: list[str] = Field(default_factory=list)
    max_results: int = Field(15, ge=1, le=50)
    min_my_ros_gain: float = Field(1, ge=0)
    min_opponent_ros_gain: float = Field(0, ge=0)
    max_value_imbalance: float = Field(.4, ge=.05, le=.8)
    consolidation_weight: float = Field(.1, ge=0, le=1)
    opponent_weight: float = Field(.35, ge=0, le=2)
    risk_weight: float = Field(.2, ge=0, le=2)
    max_dynasty_loss: float = Field(.1, ge=0, le=.3)


class TradeProposal(BaseModel):
    trade_id: str
    my_roster_id: int
    opponent_id: int
    send: list[str]
    receive: list[str]
    my_drops: list[str] = Field(default_factory=list)
    opponent_drops: list[str] = Field(default_factory=list)
    my_week_gain: float
    opponent_week_gain: float
    my_ros_gain: float
    opponent_ros_gain: float
    my_playoff_gain: float | None = None
    opponent_playoff_gain: float | None = None
    my_bench_change: float
    opponent_bench_change: float
    balance_score: float
    value_imbalance: float
    value_basis: str
    my_dynasty_gain: float | None = None
    opponent_dynasty_gain: float | None = None
    rank_score: float
    confidence: str
    my_after: Lineup
    opponent_after: Lineup
    reasons: list[str]
    risks: list[str]


class TradeRun(BaseModel):
    league_id: str
    my_roster_id: int
    as_of: datetime = Field(default_factory=utcnow)
    snapshot_at: datetime
    start_week: int
    end_week: int
    evaluations: dict[str, Evaluation]
    teams: list[TeamReport]
    trades: list[TradeProposal]
    replacement: dict[str, float]
    sources: list[SourceInfo]
    warnings: list[str]
    candidates_evaluated: int = 0
