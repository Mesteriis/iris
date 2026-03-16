from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class RelationCandidateReadModel:
    coin_id: int
    symbol: str


@dataclass(slots=True, frozen=True)
class RelationComputationContextReadModel:
    follower_coin_id: int
    follower_symbol: str
    sector_id: int | None
    candidates: tuple[RelationCandidateReadModel, ...]


@dataclass(slots=True, frozen=True)
class ExistingRelationSnapshotReadModel:
    leader_coin_id: int
    follower_coin_id: int
    correlation: float
    lag_hours: int
    confidence: float
    updated_at: datetime | None


@dataclass(slots=True, frozen=True)
class SectorMomentumAggregateReadModel:
    sector_id: int
    sector_name: str
    avg_price_change_24h: float
    avg_volume_change_24h: float
    avg_volatility: float
    sector_strength: float
    capital_flow: float


@dataclass(slots=True, frozen=True)
class SectorLeaderReadModel:
    sector_id: int
    sector_name: str
    relative_strength: float


@dataclass(slots=True, frozen=True)
class LeaderDecisionReadModel:
    leader_coin_id: int
    decision: str
    confidence: float


@dataclass(slots=True, frozen=True)
class LeaderDetectionContextReadModel:
    coin_id: int
    symbol: str
    activity_bucket: str | None
    price_change_24h: float
    volume_change_24h: float
    market_regime: str | None
    sector_id: int | None


__all__ = [
    "ExistingRelationSnapshotReadModel",
    "LeaderDecisionReadModel",
    "LeaderDetectionContextReadModel",
    "RelationCandidateReadModel",
    "RelationComputationContextReadModel",
    "SectorLeaderReadModel",
    "SectorMomentumAggregateReadModel",
]
