from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CrossMarketRelationAnalysisResult:
    correlation: float
    lag_hours: int
    sample_size: int
    confidence: float


@dataclass(slots=True, frozen=True)
class CrossMarketSectorMomentumAggregateInput:
    sector_id: int
    sector_name: str
    avg_price_change_24h: float
    avg_volume_change_24h: float
    avg_volatility: float
    capital_flow: float


@dataclass(slots=True, frozen=True)
class CrossMarketSectorMomentumRow:
    sector_id: int
    timeframe: int
    sector_strength: float
    relative_strength: float
    capital_flow: float
    avg_price_change_24h: float
    avg_volume_change_24h: float
    volatility: float
    trend: str


@dataclass(slots=True, frozen=True)
class CrossMarketTopSectorResult:
    sector_id: int
    sector_name: str
    relative_strength: float


@dataclass(slots=True, frozen=True)
class CrossMarketSectorMomentumEngineResult:
    rows: tuple[CrossMarketSectorMomentumRow, ...]
    top_sector: CrossMarketTopSectorResult | None


@dataclass(slots=True, frozen=True)
class CrossMarketLeaderDetectionInput:
    activity_bucket: str
    price_change_24h: float
    volume_change_24h: float
    market_regime: str


@dataclass(slots=True, frozen=True)
class CrossMarketLeaderDetectionResult:
    status: str
    reason: str | None = None
    direction: str | None = None
    confidence: float | None = None


__all__ = [
    "CrossMarketLeaderDetectionInput",
    "CrossMarketLeaderDetectionResult",
    "CrossMarketRelationAnalysisResult",
    "CrossMarketSectorMomentumAggregateInput",
    "CrossMarketSectorMomentumEngineResult",
    "CrossMarketSectorMomentumRow",
    "CrossMarketTopSectorResult",
]
