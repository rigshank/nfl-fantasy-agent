from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Player(BaseModel):
    player_id: str
    name: str
    positions: list[str] = Field(default_factory=list)
    team: str | None = None
    status: str | None = None
    injury_status: str | None = None
    active: bool = True
    known: bool = True


class Roster(BaseModel):
    roster_id: int
    owner_id: str | None = None
    co_owners: list[str] = Field(default_factory=list)
    manager: str
    players: list[str] = Field(default_factory=list)
    starters: list[str] = Field(default_factory=list)
    reserve: list[str] = Field(default_factory=list)
    taxi: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Snapshot(BaseModel):
    league_id: str
    name: str
    season: str
    week: int
    league_type: str
    league_status: str | None = None
    roster_positions: list[str]
    scoring: dict[str, float]
    settings: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    rosters: list[Roster]
    players: dict[str, Player]
    matchups: list[dict] = Field(default_factory=list)
    transactions: list[dict] = Field(default_factory=list)
    traded_picks: list[dict] = Field(default_factory=list)
    drafts: list[dict] = Field(default_factory=list)
    refreshed_at: datetime = Field(default_factory=utcnow)
    catalog_at: datetime = Field(default_factory=utcnow)
    warnings: list[str] = Field(default_factory=list)


class ResearchResult(BaseModel):
    title: str
    url: str
    excerpt: str
    published_at: str | None = None
    retrieved_at: datetime = Field(default_factory=utcnow)


class ResearchBundle(BaseModel):
    query: str
    sources: list[ResearchResult] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=utcnow)


class PlayerStats(BaseModel):
    """Phase 2 contract: missing fields stay missing, never silently zero-filled."""
    player_id: str
    season: int
    week: int
    observed: dict[str, float | None]
    source_url: str
    as_of: datetime


class Recommendation(BaseModel):
    kind: str
    explanation: str
    confidence: Literal["low", "medium", "high"]
    evidence_urls: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
