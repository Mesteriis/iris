from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.apps.market_data.models import Coin
from src.apps.signals.models import RiskMetric
from src.apps.signals.query_builders import latest_final_signals_subquery
from src.apps.signals.read_models import (
    CoinFinalSignalItemReadModel,
    CoinFinalSignalReadModel,
    coin_final_signal_item_read_model_from_mapping,
    coin_final_signal_payload,
    final_signal_payload,
    final_signal_read_model_from_mapping,
)
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value


def _latest_final_signals_subquery():
    return latest_final_signals_subquery()


def _canonical_decision(items: Sequence[CoinFinalSignalItemReadModel]) -> str | None:
    items_by_timeframe = {int(item.timeframe): str(item.decision) for item in items}
    for current_timeframe in (1440, 240, 60, 15):
        if current_timeframe in items_by_timeframe:
            return items_by_timeframe[current_timeframe]
    return None


class FinalSignalCompatibilityQuery:
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
                    "component": "FinalSignalCompatibilityQuery",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def list_final_signals(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_final_signals.deprecated",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        self._log(
            logging.DEBUG,
            "compat.list_final_signals.execute",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        latest = _latest_final_signals_subquery()
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
                latest.c.risk_adjusted_score,
                RiskMetric.liquidity_score,
                RiskMetric.slippage_risk,
                RiskMetric.volatility_risk,
                latest.c.reason,
                latest.c.created_at,
            )
            .join(Coin, Coin.id == latest.c.coin_id)
            .outerjoin(
                RiskMetric,
                and_(
                    RiskMetric.coin_id == latest.c.coin_id,
                    RiskMetric.timeframe == latest.c.timeframe,
                ),
            )
            .where(latest.c.final_signal_rank == 1, Coin.deleted_at.is_(None))
            .order_by(latest.c.created_at.desc(), latest.c.id.desc())
            .limit(max(limit, 1))
        )
        if symbol is not None:
            stmt = stmt.where(Coin.symbol == symbol.upper())
        if timeframe is not None:
            stmt = stmt.where(latest.c.timeframe == timeframe)
        rows = self._db.execute(stmt).all()
        result = [final_signal_payload(final_signal_read_model_from_mapping(row._mapping)) for row in rows]
        self._log(logging.INFO, "compat.list_final_signals.result", mode="read", count=len(result))
        return result

    def list_top_final_signals(self, *, limit: int = 20) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_top_final_signals.deprecated",
            mode="read",
            limit=limit,
        )
        self._log(
            logging.DEBUG,
            "compat.list_top_final_signals.execute",
            mode="read",
            limit=limit,
        )
        latest = _latest_final_signals_subquery()
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
                latest.c.risk_adjusted_score,
                RiskMetric.liquidity_score,
                RiskMetric.slippage_risk,
                RiskMetric.volatility_risk,
                latest.c.reason,
                latest.c.created_at,
            )
            .join(Coin, Coin.id == latest.c.coin_id)
            .outerjoin(
                RiskMetric,
                and_(
                    RiskMetric.coin_id == latest.c.coin_id,
                    RiskMetric.timeframe == latest.c.timeframe,
                ),
            )
            .where(latest.c.final_signal_rank == 1, Coin.deleted_at.is_(None))
            .order_by(latest.c.risk_adjusted_score.desc(), latest.c.confidence.desc(), latest.c.created_at.desc())
            .limit(max(limit, 1))
        ).all()
        result = [final_signal_payload(final_signal_read_model_from_mapping(row._mapping)) for row in rows]
        self._log(logging.INFO, "compat.list_top_final_signals.result", mode="read", count=len(result))
        return result

    def get_coin_final_signal(self, symbol: str) -> dict[str, Any] | None:
        normalized_symbol = symbol.strip().upper()
        self._log(
            logging.WARNING,
            "compat.get_coin_final_signal.deprecated",
            mode="read",
            symbol=normalized_symbol,
        )
        self._log(
            logging.DEBUG,
            "compat.get_coin_final_signal.execute",
            mode="read",
            symbol=normalized_symbol,
        )
        coin = self._db.scalar(select(Coin).where(Coin.symbol == normalized_symbol, Coin.deleted_at.is_(None)).limit(1))
        if coin is None:
            self._log(logging.INFO, "compat.get_coin_final_signal.result", mode="read", symbol=normalized_symbol, found=False)
            return None
        latest = _latest_final_signals_subquery()
        rows = self._db.execute(
            select(
                latest.c.timeframe,
                latest.c.decision,
                latest.c.confidence,
                latest.c.risk_adjusted_score,
                RiskMetric.liquidity_score,
                RiskMetric.slippage_risk,
                RiskMetric.volatility_risk,
                latest.c.reason,
                latest.c.created_at,
            )
            .outerjoin(
                RiskMetric,
                and_(
                    RiskMetric.coin_id == latest.c.coin_id,
                    RiskMetric.timeframe == latest.c.timeframe,
                ),
            )
            .where(latest.c.coin_id == coin.id, latest.c.final_signal_rank == 1)
            .order_by(latest.c.timeframe.asc())
        ).all()
        items = tuple(coin_final_signal_item_read_model_from_mapping(row._mapping) for row in rows)
        item = CoinFinalSignalReadModel(
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            canonical_decision=_canonical_decision(items),
            items=items,
        )
        result = coin_final_signal_payload(item)
        self._log(
            logging.INFO,
            "compat.get_coin_final_signal.result",
            mode="read",
            symbol=normalized_symbol,
            found=True,
            count=len(result["items"]),
        )
        return result


def list_final_signals(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    return FinalSignalCompatibilityQuery(db).list_final_signals(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


def list_top_final_signals(db: Session, *, limit: int = 20) -> Sequence[dict[str, Any]]:
    return FinalSignalCompatibilityQuery(db).list_top_final_signals(limit=limit)


def get_coin_final_signal(db: Session, symbol: str) -> dict[str, Any] | None:
    return FinalSignalCompatibilityQuery(db).get_coin_final_signal(symbol)


__all__ = [
    "FinalSignalCompatibilityQuery",
    "_latest_final_signals_subquery",
    "get_coin_final_signal",
    "list_final_signals",
    "list_top_final_signals",
]
