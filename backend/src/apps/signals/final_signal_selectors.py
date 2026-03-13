from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.apps.market_data.models import Coin
from src.apps.market_data.service_layer import get_coin_by_symbol
from src.apps.signals.models import RiskMetric
from src.apps.signals.query_builders import latest_final_signals_subquery
from src.apps.signals.read_models import (
    CoinFinalSignalItemReadModel,
    CoinFinalSignalReadModel,
    FinalSignalReadModel,
    coin_final_signal_item_read_model_from_mapping,
    final_signal_read_model_from_mapping,
)
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value


def _latest_final_signals_subquery():
    return latest_final_signals_subquery()


def _final_signal_payload(item: FinalSignalReadModel) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "coin_id": int(item.coin_id),
        "symbol": str(item.symbol),
        "name": str(item.name),
        "sector": item.sector,
        "timeframe": int(item.timeframe),
        "decision": str(item.decision),
        "confidence": float(item.confidence),
        "risk_adjusted_score": float(item.risk_adjusted_score),
        "liquidity_score": float(item.liquidity_score),
        "slippage_risk": float(item.slippage_risk),
        "volatility_risk": float(item.volatility_risk),
        "reason": str(item.reason),
        "created_at": item.created_at,
    }


def _coin_final_signal_item_payload(item: CoinFinalSignalItemReadModel) -> dict[str, Any]:
    return {
        "timeframe": int(item.timeframe),
        "decision": str(item.decision),
        "confidence": float(item.confidence),
        "risk_adjusted_score": float(item.risk_adjusted_score),
        "liquidity_score": float(item.liquidity_score),
        "slippage_risk": float(item.slippage_risk),
        "volatility_risk": float(item.volatility_risk),
        "reason": str(item.reason),
        "created_at": item.created_at,
    }


def _canonical_decision(items: Sequence[CoinFinalSignalItemReadModel]) -> str | None:
    items_by_timeframe = {int(item.timeframe): str(item.decision) for item in items}
    for current_timeframe in (1440, 240, 60, 15):
        if current_timeframe in items_by_timeframe:
            return items_by_timeframe[current_timeframe]
    return None


def _coin_final_signal_payload(item: CoinFinalSignalReadModel) -> dict[str, Any]:
    return {
        "coin_id": int(item.coin_id),
        "symbol": str(item.symbol),
        "canonical_decision": item.canonical_decision,
        "items": [_coin_final_signal_item_payload(model) for model in item.items],
    }


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
        return [_final_signal_payload(final_signal_read_model_from_mapping(row._mapping)) for row in rows]

    def list_top_final_signals(self, *, limit: int = 20) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_top_final_signals.deprecated",
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
        return [_final_signal_payload(final_signal_read_model_from_mapping(row._mapping)) for row in rows]

    def get_coin_final_signal(self, symbol: str) -> dict[str, Any] | None:
        normalized_symbol = symbol.strip().upper()
        self._log(
            logging.WARNING,
            "compat.get_coin_final_signal.deprecated",
            mode="read",
            symbol=normalized_symbol,
        )
        coin = get_coin_by_symbol(self._db, normalized_symbol)
        if coin is None:
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
        return _coin_final_signal_payload(item)


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
