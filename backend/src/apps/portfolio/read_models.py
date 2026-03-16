from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class PortfolioPositionReadModel:
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None
    exchange_account_id: int | None
    source_exchange: str | None
    position_type: str
    timeframe: int
    entry_price: float
    position_size: float
    position_value: float
    stop_loss: float | None
    take_profit: float | None
    status: str
    opened_at: datetime
    closed_at: datetime | None
    current_price: float | None
    unrealized_pnl: float
    latest_decision: str | None
    latest_decision_confidence: float | None
    regime: str | None
    risk_to_stop: float | None


@dataclass(slots=True, frozen=True)
class PortfolioActionReadModel:
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


@dataclass(slots=True, frozen=True)
class PortfolioStateReadModel:
    total_capital: float
    allocated_capital: float
    available_capital: float
    updated_at: str | None
    open_positions: int
    max_positions: int


def portfolio_position_read_model_from_mapping(mapping: Mapping[str, Any]) -> PortfolioPositionReadModel:
    return PortfolioPositionReadModel(
        id=int(mapping["id"]),
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        sector=str(mapping["sector"]) if mapping["sector"] is not None else None,
        exchange_account_id=int(mapping["exchange_account_id"]) if mapping["exchange_account_id"] is not None else None,
        source_exchange=str(mapping["source_exchange"]) if mapping["source_exchange"] is not None else None,
        position_type=str(mapping["position_type"]),
        timeframe=int(mapping["timeframe"]),
        entry_price=float(mapping["entry_price"]),
        position_size=float(mapping["position_size"]),
        position_value=float(mapping["position_value"]),
        stop_loss=float(mapping["stop_loss"]) if mapping["stop_loss"] is not None else None,
        take_profit=float(mapping["take_profit"]) if mapping["take_profit"] is not None else None,
        status=str(mapping["status"]),
        opened_at=mapping["opened_at"],
        closed_at=mapping["closed_at"],
        current_price=float(mapping["current_price"]) if mapping["current_price"] is not None else None,
        unrealized_pnl=float(mapping["unrealized_pnl"]),
        latest_decision=str(mapping["latest_decision"]) if mapping["latest_decision"] is not None else None,
        latest_decision_confidence=(
            float(mapping["latest_decision_confidence"])
            if mapping["latest_decision_confidence"] is not None
            else None
        ),
        regime=str(mapping["regime"]) if mapping["regime"] is not None else None,
        risk_to_stop=float(mapping["risk_to_stop"]) if mapping["risk_to_stop"] is not None else None,
    )


def portfolio_action_read_model_from_mapping(mapping: Mapping[str, Any]) -> PortfolioActionReadModel:
    return PortfolioActionReadModel(
        id=int(mapping["id"]),
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        action=str(mapping["action"]),
        size=float(mapping["size"]),
        confidence=float(mapping["confidence"]),
        decision_id=int(mapping["decision_id"]),
        market_decision=str(mapping["market_decision"]),
        created_at=mapping["created_at"],
    )


def portfolio_state_read_model_from_mapping(mapping: Mapping[str, Any]) -> PortfolioStateReadModel:
    return PortfolioStateReadModel(
        total_capital=float(mapping["total_capital"]),
        allocated_capital=float(mapping["allocated_capital"]),
        available_capital=float(mapping["available_capital"]),
        updated_at=str(mapping["updated_at"]) if mapping["updated_at"] is not None else None,
        open_positions=int(mapping["open_positions"]),
        max_positions=int(mapping["max_positions"]),
    )


def portfolio_position_payload(item: PortfolioPositionReadModel) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "coin_id": int(item.coin_id),
        "symbol": str(item.symbol),
        "name": str(item.name),
        "sector": item.sector,
        "exchange_account_id": int(item.exchange_account_id) if item.exchange_account_id is not None else None,
        "source_exchange": item.source_exchange,
        "position_type": str(item.position_type),
        "timeframe": int(item.timeframe),
        "entry_price": float(item.entry_price),
        "position_size": float(item.position_size),
        "position_value": float(item.position_value),
        "stop_loss": float(item.stop_loss) if item.stop_loss is not None else None,
        "take_profit": float(item.take_profit) if item.take_profit is not None else None,
        "status": str(item.status),
        "opened_at": item.opened_at,
        "closed_at": item.closed_at,
        "current_price": float(item.current_price) if item.current_price is not None else None,
        "unrealized_pnl": float(item.unrealized_pnl),
        "latest_decision": item.latest_decision,
        "latest_decision_confidence": (
            float(item.latest_decision_confidence) if item.latest_decision_confidence is not None else None
        ),
        "regime": item.regime,
        "risk_to_stop": float(item.risk_to_stop) if item.risk_to_stop is not None else None,
    }


def portfolio_action_payload(item: PortfolioActionReadModel) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "coin_id": int(item.coin_id),
        "symbol": str(item.symbol),
        "name": str(item.name),
        "action": str(item.action),
        "size": float(item.size),
        "confidence": float(item.confidence),
        "decision_id": int(item.decision_id),
        "market_decision": str(item.market_decision),
        "created_at": item.created_at,
    }


def portfolio_state_payload(item: PortfolioStateReadModel) -> dict[str, Any]:
    return {
        "total_capital": float(item.total_capital),
        "allocated_capital": float(item.allocated_capital),
        "available_capital": float(item.available_capital),
        "updated_at": item.updated_at,
        "open_positions": int(item.open_positions),
        "max_positions": int(item.max_positions),
    }


__all__ = [
    "PortfolioActionReadModel",
    "PortfolioPositionReadModel",
    "PortfolioStateReadModel",
    "portfolio_action_payload",
    "portfolio_action_read_model_from_mapping",
    "portfolio_position_payload",
    "portfolio_position_read_model_from_mapping",
    "portfolio_state_payload",
    "portfolio_state_read_model_from_mapping",
]
