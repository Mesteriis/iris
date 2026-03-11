from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SignalRead(BaseModel):
    coin_id: int
    symbol: str
    name: str
    timeframe: int
    signal_type: str
    confidence: float
    candle_timestamp: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
