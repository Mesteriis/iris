from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MarketDecisionRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinMarketDecisionItemRead(BaseModel):
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CoinMarketDecisionRead(BaseModel):
    coin_id: int
    symbol: str
    canonical_decision: str | None = None
    items: list[CoinMarketDecisionItemRead]

    model_config = ConfigDict(from_attributes=True)
