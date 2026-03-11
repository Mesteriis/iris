from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BacktestSummaryRead(BaseModel):
    symbol: str | None = None
    signal_type: str
    timeframe: int
    sample_size: int
    coin_count: int
    win_rate: float
    roi: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    avg_confidence: float
    last_evaluated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CoinBacktestsRead(BaseModel):
    coin_id: int
    symbol: str
    items: list[BacktestSummaryRead]

    model_config = ConfigDict(from_attributes=True)
