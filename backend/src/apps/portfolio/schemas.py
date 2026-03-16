from datetime import datetime

from pydantic import BaseModel, ConfigDict
from src.core.http.contracts import AnalyticalReadContract


class PortfolioPositionRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    exchange_account_id: int | None = None
    source_exchange: str | None = None
    position_type: str
    timeframe: int
    entry_price: float
    position_size: float
    position_value: float
    stop_loss: float | None = None
    take_profit: float | None = None
    status: str
    opened_at: datetime
    closed_at: datetime | None = None
    current_price: float | None = None
    unrealized_pnl: float
    latest_decision: str | None = None
    latest_decision_confidence: float | None = None
    regime: str | None = None
    risk_to_stop: float | None = None

    model_config = ConfigDict(from_attributes=True)


class PortfolioActionRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    action: str
    size: float
    confidence: float
    decision_id: int
    market_decision: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PortfolioStateRead(AnalyticalReadContract):
    total_capital: float
    allocated_capital: float
    available_capital: float
    updated_at: str | None = None
    open_positions: int
    max_positions: int

    model_config = ConfigDict(from_attributes=True)


__all__ = ["PortfolioActionRead", "PortfolioPositionRead", "PortfolioStateRead"]
