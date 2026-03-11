from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SignalRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    timeframe: int
    signal_type: str
    confidence: float
    priority_score: float = 0.0
    context_score: float = 0.0
    regime_alignment: float = 0.0
    candle_timestamp: datetime
    created_at: datetime
    market_regime: str | None = None
    cycle_phase: str | None = None
    cycle_confidence: float | None = None
    cluster_membership: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
