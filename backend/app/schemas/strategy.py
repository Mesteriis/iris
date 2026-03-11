from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StrategyRuleRead(BaseModel):
    pattern_slug: str
    regime: str
    sector: str
    cycle: str
    min_confidence: float

    model_config = ConfigDict(from_attributes=True)


class StrategyPerformanceRead(BaseModel):
    strategy_id: int
    name: str
    enabled: bool
    sample_size: int
    win_rate: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyRead(BaseModel):
    id: int
    name: str
    description: str
    enabled: bool
    created_at: datetime
    rules: list[StrategyRuleRead]
    performance: StrategyPerformanceRead | None = None

    model_config = ConfigDict(from_attributes=True)
