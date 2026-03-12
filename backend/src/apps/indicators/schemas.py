from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CoinMetricsRead(BaseModel):
    coin_id: int
    symbol: str
    name: str
    price_current: float | None = None
    price_change_1h: float | None = None
    price_change_24h: float | None = None
    price_change_7d: float | None = None
    ema_20: float | None = None
    ema_50: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    atr_14: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_width: float | None = None
    adx_14: float | None = None
    volume_24h: float | None = None
    volume_change_24h: float | None = None
    volatility: float | None = None
    market_cap: float | None = None
    trend: str | None = None
    trend_score: int | None = None
    activity_score: float | None = None
    activity_bucket: str | None = None
    analysis_priority: int | None = None
    last_analysis_at: datetime | None = None
    market_regime: str | None = None
    market_regime_details: dict[str, dict[str, float | str]] | None = None
    indicator_version: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MarketLeaderRead(BaseModel):
    leader_coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    regime: str | None = None
    confidence: float
    price_change_24h: float | None = None
    volume_change_24h: float | None = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinRelationRead(BaseModel):
    leader_coin_id: int
    leader_symbol: str
    follower_coin_id: int
    follower_symbol: str
    correlation: float
    lag_hours: int
    confidence: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SectorMomentumRead(BaseModel):
    sector_id: int
    sector: str
    timeframe: int
    avg_price_change_24h: float
    avg_volume_change_24h: float
    volatility: float
    trend: str | None = None
    relative_strength: float
    capital_flow: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SectorRotationRead(BaseModel):
    source_sector: str
    target_sector: str
    timeframe: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class MarketFlowRead(BaseModel):
    leaders: list[MarketLeaderRead]
    relations: list[CoinRelationRead]
    sectors: list[SectorMomentumRead]
    rotations: list[SectorRotationRead]

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class MarketRadarRead(BaseModel):
    hot_coins: list[MarketRadarCoinRead]
    emerging_coins: list[MarketRadarCoinRead]
    regime_changes: list[MarketRegimeChangeRead]
    volatility_spikes: list[MarketRadarCoinRead]

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "CoinMetricsRead",
    "CoinRelationRead",
    "MarketFlowRead",
    "MarketLeaderRead",
    "MarketRadarCoinRead",
    "MarketRadarRead",
    "MarketRegimeChangeRead",
    "SectorMomentumRead",
    "SectorRotationRead",
]
