from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InvestmentDecisionRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    timeframe: int
    decision: str
    confidence: float
    score: float
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinDecisionItemRead(BaseModel):
    timeframe: int
    decision: str
    confidence: float
    score: float
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinDecisionRead(BaseModel):
    coin_id: int
    symbol: str
    canonical_decision: str | None = None
    items: list[CoinDecisionItemRead]

    model_config = ConfigDict(from_attributes=True)
