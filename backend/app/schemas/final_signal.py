from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FinalSignalRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    timeframe: int
    decision: str
    confidence: float
    risk_adjusted_score: float
    liquidity_score: float
    slippage_risk: float
    volatility_risk: float
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinFinalSignalItemRead(BaseModel):
    timeframe: int
    decision: str
    confidence: float
    risk_adjusted_score: float
    liquidity_score: float
    slippage_risk: float
    volatility_risk: float
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinFinalSignalRead(BaseModel):
    coin_id: int
    symbol: str
    canonical_decision: str | None = None
    items: list[CoinFinalSignalItemRead]

    model_config = ConfigDict(from_attributes=True)
