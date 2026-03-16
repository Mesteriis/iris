from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MarketCycleRead(BaseModel):
    coin_id: int
    symbol: str
    name: str
    timeframe: int
    cycle_phase: str
    confidence: float
    detected_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PatternStatisticRead(BaseModel):
    timeframe: int
    market_regime: str
    sample_size: int
    total_signals: int
    successful_signals: int
    success_rate: float
    avg_return: float
    avg_drawdown: float
    temperature: float
    enabled: bool
    last_evaluated_at: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PatternRead(BaseModel):
    slug: str
    category: str
    enabled: bool
    cpu_cost: int
    lifecycle_state: str
    created_at: datetime
    statistics: list[PatternStatisticRead]

    model_config = ConfigDict(from_attributes=True)


class PatternFeatureRead(BaseModel):
    feature_slug: str
    enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PatternFeatureUpdate(BaseModel):
    enabled: bool


class PatternUpdate(BaseModel):
    enabled: bool | None = None
    lifecycle_state: str | None = None
    cpu_cost: int | None = None


class DiscoveredPatternRead(BaseModel):
    structure_hash: str
    timeframe: int
    sample_size: int
    avg_return: float
    avg_drawdown: float
    confidence: float

    model_config = ConfigDict(from_attributes=True)


class RegimeTimeframeRead(BaseModel):
    timeframe: int
    regime: str
    confidence: float

    model_config = ConfigDict(from_attributes=True)


class CoinRegimeRead(BaseModel):
    coin_id: int
    symbol: str
    canonical_regime: str | None = None
    items: list[RegimeTimeframeRead]

    model_config = ConfigDict(from_attributes=True)


class SectorRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime
    coin_count: int

    model_config = ConfigDict(from_attributes=True)


class SectorMetricRead(BaseModel):
    sector_id: int
    name: str
    description: str | None = None
    timeframe: int
    sector_strength: float
    relative_strength: float
    capital_flow: float
    avg_price_change_24h: float
    avg_volume_change_24h: float
    volatility: float
    trend: str | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SectorNarrativeRead(BaseModel):
    timeframe: int
    top_sector: str | None = None
    rotation_state: str | None = None
    btc_dominance: float | None = None
    capital_wave: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SectorMetricsResponse(BaseModel):
    items: list[SectorMetricRead]
    narratives: list[SectorNarrativeRead]

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "CoinRegimeRead",
    "DiscoveredPatternRead",
    "MarketCycleRead",
    "PatternFeatureRead",
    "PatternFeatureUpdate",
    "PatternRead",
    "PatternUpdate",
    "SectorMetricRead",
    "SectorMetricsResponse",
    "SectorNarrativeRead",
    "SectorRead",
]
