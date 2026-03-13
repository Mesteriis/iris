from __future__ import annotations

import logging
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.apps.portfolio.models import PortfolioState
from src.apps.portfolio.cache import read_cached_portfolio_state
from src.apps.portfolio.models import PortfolioAction, PortfolioPosition
from src.apps.portfolio.query_builders import (
    portfolio_actions_select as _portfolio_actions_select,
    portfolio_positions_select as _portfolio_positions_select,
)
from src.apps.portfolio.read_models import (
    PortfolioActionReadModel,
    PortfolioPositionReadModel,
    PortfolioStateReadModel,
    portfolio_action_read_model_from_mapping,
    portfolio_position_read_model_from_mapping,
    portfolio_state_read_model_from_mapping,
)
from src.apps.patterns.domain.regime import read_regime_details
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value
from src.core.settings import get_settings


def _portfolio_position_payload(item: PortfolioPositionReadModel) -> dict[str, Any]:
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


def _portfolio_action_payload(item: PortfolioActionReadModel) -> dict[str, Any]:
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


def _portfolio_state_payload(item: PortfolioStateReadModel) -> dict[str, Any]:
    return {
        "total_capital": float(item.total_capital),
        "allocated_capital": float(item.allocated_capital),
        "available_capital": float(item.available_capital),
        "updated_at": item.updated_at,
        "open_positions": int(item.open_positions),
        "max_positions": int(item.max_positions),
    }


class PortfolioCompatibilityQuery:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        PERSISTENCE_LOGGER.log(
            level,
            event,
            extra={
                "persistence": {
                    "event": event,
                    "component_type": "compatibility_query",
                    "domain": "portfolio",
                    "component": "PortfolioCompatibilityQuery",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def list_positions(self, *, limit: int = 200) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_portfolio_positions.deprecated",
            mode="read",
            limit=limit,
        )
        rows = (
            self._db.execute(
                _portfolio_positions_select()
                .where(PortfolioPosition.status.in_(("open", "partial")))
                .order_by(PortfolioPosition.position_value.desc(), PortfolioPosition.id.desc())
                .limit(max(limit, 1))
            )
        ).all()
        items = []
        for row in rows:
            current_price = float(row.price_current or 0.0)
            entry_price = float(row.entry_price or 0.0)
            detailed = read_regime_details(row.market_regime_details, int(row.timeframe))
            items.append(
                portfolio_position_read_model_from_mapping(
                    {
                        **row._mapping,
                        "entry_price": entry_price,
                        "current_price": current_price or None,
                        "unrealized_pnl": (
                            (current_price - entry_price) * float(row.position_size or 0.0)
                            if current_price and entry_price
                            else 0.0
                        ),
                        "regime": detailed.regime if detailed is not None else row.market_regime,
                        "risk_to_stop": (
                            max((entry_price - float(row.stop_loss or 0.0)) / entry_price, 0.0)
                            if entry_price and row.stop_loss is not None
                            else None
                        ),
                    }
                )
            )
        return [_portfolio_position_payload(item) for item in items]

    def list_actions(self, *, limit: int = 200) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_portfolio_actions.deprecated",
            mode="read",
            limit=limit,
        )
        rows = (
            self._db.execute(
                _portfolio_actions_select()
                .order_by(PortfolioAction.created_at.desc(), PortfolioAction.id.desc())
                .limit(max(limit, 1))
            )
        ).all()
        return [_portfolio_action_payload(portfolio_action_read_model_from_mapping(row._mapping)) for row in rows]

    def get_state(self) -> dict[str, Any]:
        self._log(
            logging.WARNING,
            "compat.get_portfolio_state.deprecated",
            mode="read",
        )
        cached = read_cached_portfolio_state()
        if cached is not None:
            return cached
        state = self._db.get(PortfolioState, 1)
        if state is None:
            return _portfolio_state_payload(
                PortfolioStateReadModel(
                    total_capital=0.0,
                    allocated_capital=0.0,
                    available_capital=0.0,
                    updated_at=None,
                    open_positions=0,
                    max_positions=0,
                )
            )
        open_positions = int(
            self._db.scalar(
                select(func.count()).select_from(PortfolioPosition).where(PortfolioPosition.status.in_(("open", "partial")))
            )
            or 0
        )
        return _portfolio_state_payload(
            portfolio_state_read_model_from_mapping(
                {
                    "total_capital": float(state.total_capital),
                    "allocated_capital": float(state.allocated_capital),
                    "available_capital": float(state.available_capital),
                    "updated_at": state.updated_at.isoformat(),
                    "open_positions": open_positions,
                    "max_positions": int(get_settings().portfolio_max_positions),
                }
            )
        )


def list_portfolio_positions(db: Session, *, limit: int = 200) -> Sequence[dict[str, Any]]:
    return PortfolioCompatibilityQuery(db).list_positions(limit=limit)


def list_portfolio_actions(db: Session, *, limit: int = 200) -> Sequence[dict[str, Any]]:
    return PortfolioCompatibilityQuery(db).list_actions(limit=limit)


def get_portfolio_state(db: Session) -> dict[str, Any]:
    return PortfolioCompatibilityQuery(db).get_state()


__all__ = [
    "PortfolioCompatibilityQuery",
    "get_portfolio_state",
    "list_portfolio_actions",
    "list_portfolio_positions",
]
