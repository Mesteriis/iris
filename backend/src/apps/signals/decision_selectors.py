from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.apps.market_data.models import Coin
from src.apps.signals.query_builders import latest_decisions_subquery
from src.apps.signals.read_models import (
    CoinDecisionItemReadModel,
    CoinDecisionReadModel,
    coin_decision_payload,
    coin_decision_item_read_model_from_mapping,
    investment_decision_payload,
    investment_decision_read_model_from_mapping,
)
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value


def _latest_decisions_subquery():
    return latest_decisions_subquery()


def _canonical_decision(items: Sequence[CoinDecisionItemReadModel]) -> str | None:
    items_by_timeframe = {int(item.timeframe): str(item.decision) for item in items}
    for current_timeframe in (1440, 240, 60, 15):
        if current_timeframe in items_by_timeframe:
            return items_by_timeframe[current_timeframe]
    return None


class SignalDecisionCompatibilityQuery:
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
                    "domain": "signals",
                    "component": "SignalDecisionCompatibilityQuery",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def list_decisions(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_decisions.deprecated",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        latest = _latest_decisions_subquery()
        stmt = (
            select(
                latest.c.id,
                latest.c.coin_id,
                Coin.symbol,
                Coin.name,
                Coin.sector_code.label("sector"),
                latest.c.timeframe,
                latest.c.decision,
                latest.c.confidence,
                latest.c.score,
                latest.c.reason,
                latest.c.created_at,
            )
            .join(Coin, Coin.id == latest.c.coin_id)
            .where(latest.c.decision_rank == 1, Coin.deleted_at.is_(None))
            .order_by(latest.c.created_at.desc(), latest.c.id.desc())
            .limit(max(limit, 1))
        )
        if symbol is not None:
            stmt = stmt.where(Coin.symbol == symbol.upper())
        if timeframe is not None:
            stmt = stmt.where(latest.c.timeframe == timeframe)
        rows = self._db.execute(stmt).all()
        return [investment_decision_payload(investment_decision_read_model_from_mapping(row._mapping)) for row in rows]

    def list_top_decisions(self, *, limit: int = 20) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_top_decisions.deprecated",
            mode="read",
            limit=limit,
        )
        latest = _latest_decisions_subquery()
        rows = self._db.execute(
            select(
                latest.c.id,
                latest.c.coin_id,
                Coin.symbol,
                Coin.name,
                Coin.sector_code.label("sector"),
                latest.c.timeframe,
                latest.c.decision,
                latest.c.confidence,
                latest.c.score,
                latest.c.reason,
                latest.c.created_at,
            )
            .join(Coin, Coin.id == latest.c.coin_id)
            .where(latest.c.decision_rank == 1, Coin.deleted_at.is_(None))
            .order_by(latest.c.score.desc(), latest.c.confidence.desc(), latest.c.created_at.desc())
            .limit(max(limit, 1))
        ).all()
        return [investment_decision_payload(investment_decision_read_model_from_mapping(row._mapping)) for row in rows]

    def get_coin_decision(self, symbol: str) -> dict[str, Any] | None:
        normalized_symbol = symbol.strip().upper()
        self._log(
            logging.WARNING,
            "compat.get_coin_decision.deprecated",
            mode="read",
            symbol=normalized_symbol,
        )
        coin = self._db.scalar(select(Coin).where(Coin.symbol == normalized_symbol, Coin.deleted_at.is_(None)).limit(1))
        if coin is None:
            return None
        latest = _latest_decisions_subquery()
        rows = self._db.execute(
            select(
                latest.c.timeframe,
                latest.c.decision,
                latest.c.confidence,
                latest.c.score,
                latest.c.reason,
                latest.c.created_at,
            )
            .where(latest.c.coin_id == coin.id, latest.c.decision_rank == 1)
            .order_by(latest.c.timeframe.asc())
        ).all()
        items = tuple(coin_decision_item_read_model_from_mapping(row._mapping) for row in rows)
        item = CoinDecisionReadModel(
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            canonical_decision=_canonical_decision(items),
            items=items,
        )
        return coin_decision_payload(item)


def list_decisions(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    return SignalDecisionCompatibilityQuery(db).list_decisions(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


def list_top_decisions(db: Session, *, limit: int = 20) -> Sequence[dict[str, Any]]:
    return SignalDecisionCompatibilityQuery(db).list_top_decisions(limit=limit)


def get_coin_decision(db: Session, symbol: str) -> dict[str, Any] | None:
    return SignalDecisionCompatibilityQuery(db).get_coin_decision(symbol)


__all__ = [
    "SignalDecisionCompatibilityQuery",
    "_latest_decisions_subquery",
    "get_coin_decision",
    "list_decisions",
    "list_top_decisions",
]
