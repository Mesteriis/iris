from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PatternStatisticRead(BaseModel):
    timeframe: int
    sample_size: int
    success_rate: float
    avg_return: float
    avg_drawdown: float
    temperature: float
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
