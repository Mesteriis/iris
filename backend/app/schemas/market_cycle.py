from __future__ import annotations

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
