from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
