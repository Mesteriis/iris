from dataclasses import dataclass

from src.apps.predictions.services.results import PredictionCreationBatch


@dataclass(slots=True, frozen=True)
class CrossMarketRelationUpdateResult:
    status: str
    follower_coin_id: int | None = None
    updated: int = 0
    published: int = 0
    leader_coin_id: int | None = None
    confidence: float | None = None
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class CrossMarketSectorMomentumResult:
    status: str
    updated: int = 0
    timeframe: int | None = None
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class CrossMarketLeaderDetectionResult:
    status: str
    coin_id: int | None = None
    leader_coin_id: int | None = None
    direction: str | None = None
    confidence: float | None = None
    predictions: PredictionCreationBatch | None = None
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class CrossMarketProcessResult:
    status: str
    relations: CrossMarketRelationUpdateResult
    sectors: CrossMarketSectorMomentumResult
    leader: CrossMarketLeaderDetectionResult


__all__ = [
    "CrossMarketLeaderDetectionResult",
    "CrossMarketProcessResult",
    "CrossMarketRelationUpdateResult",
    "CrossMarketSectorMomentumResult",
]
