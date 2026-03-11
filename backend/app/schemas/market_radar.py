from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MarketRadarCoinRead(BaseModel):
    coin_id: int
    symbol: str
    name: str
    activity_score: float | None = None
    activity_bucket: str | None = None
    analysis_priority: int | None = None
    price_change_24h: float | None = None
    price_change_7d: float | None = None
    volatility: float | None = None
    market_regime: str | None = None
    updated_at: datetime | None = None
    last_analysis_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MarketRegimeChangeRead(BaseModel):
    coin_id: int
    symbol: str
    name: str
    timeframe: int
    regime: str
    confidence: float
    timestamp: datetime


class MarketRadarRead(BaseModel):
    hot_coins: list[MarketRadarCoinRead]
    emerging_coins: list[MarketRadarCoinRead]
    regime_changes: list[MarketRegimeChangeRead]
    volatility_spikes: list[MarketRadarCoinRead]
