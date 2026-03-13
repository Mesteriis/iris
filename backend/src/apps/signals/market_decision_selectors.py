from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.patterns.domain.regime import read_regime_details
from src.apps.signals.cache import read_cached_market_decision
from src.apps.signals.query_builders import latest_market_decisions_subquery
from src.apps.signals.read_models import (
    CoinMarketDecisionItemReadModel,
    CoinMarketDecisionReadModel,
    coin_market_decision_item_read_model_from_mapping,
    coin_market_decision_payload,
    market_decision_payload,
    market_decision_read_model_from_mapping,
)
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value

PREFERRED_TIMEFRAMES = (1440, 240, 60, 15)


def _latest_market_decisions_subquery():
    return latest_market_decisions_subquery()


def _canonical_decision(items: Sequence[CoinMarketDecisionItemReadModel]) -> str | None:
    items_by_timeframe = {int(item.timeframe): str(item.decision) for item in items}
    for current_timeframe in PREFERRED_TIMEFRAMES:
        if current_timeframe in items_by_timeframe:
            return items_by_timeframe[current_timeframe]
    return None


class MarketDecisionCompatibilityQuery:
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
                    "component": "MarketDecisionCompatibilityQuery",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def list_market_decisions(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_market_decisions.deprecated",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        latest = _latest_market_decisions_subquery()
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
                latest.c.signal_count,
                CoinMetrics.market_regime.label("regime"),
                latest.c.created_at,
            )
            .join(Coin, Coin.id == latest.c.coin_id)
            .outerjoin(CoinMetrics, CoinMetrics.coin_id == latest.c.coin_id)
            .where(latest.c.market_decision_rank == 1, Coin.deleted_at.is_(None))
            .order_by(latest.c.created_at.desc(), latest.c.id.desc())
            .limit(max(limit, 1))
        )
        if symbol is not None:
            stmt = stmt.where(Coin.symbol == symbol.upper())
        if timeframe is not None:
            stmt = stmt.where(latest.c.timeframe == timeframe)
        rows = self._db.execute(stmt).all()
        return [market_decision_payload(market_decision_read_model_from_mapping(row._mapping)) for row in rows]

    def list_top_market_decisions(self, *, limit: int = 20) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_top_market_decisions.deprecated",
            mode="read",
            limit=limit,
        )
        latest = _latest_market_decisions_subquery()
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
                latest.c.signal_count,
                CoinMetrics.market_regime.label("regime"),
                latest.c.created_at,
            )
            .join(Coin, Coin.id == latest.c.coin_id)
            .outerjoin(CoinMetrics, CoinMetrics.coin_id == latest.c.coin_id)
            .where(latest.c.market_decision_rank == 1, Coin.deleted_at.is_(None))
            .order_by(latest.c.confidence.desc(), latest.c.signal_count.desc(), latest.c.created_at.desc())
            .limit(max(limit, 1))
        ).all()
        return [market_decision_payload(market_decision_read_model_from_mapping(row._mapping)) for row in rows]

    def get_coin_market_decision(self, symbol: str) -> dict[str, Any] | None:
        normalized_symbol = symbol.strip().upper()
        self._log(
            logging.WARNING,
            "compat.get_coin_market_decision.deprecated",
            mode="read",
            symbol=normalized_symbol,
        )
        coin = self._db.scalar(select(Coin).where(Coin.symbol == normalized_symbol, Coin.deleted_at.is_(None)).limit(1))
        if coin is None:
            return None
        metrics = self._db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
        cached_items: list[CoinMarketDecisionItemReadModel] = []
        for timeframe in PREFERRED_TIMEFRAMES:
            cached = read_cached_market_decision(coin_id=coin.id, timeframe=timeframe)
            if cached is None:
                continue
            detailed = read_regime_details(metrics.market_regime_details, timeframe) if metrics is not None else None
            cached_items.append(
                CoinMarketDecisionItemReadModel(
                    timeframe=int(timeframe),
                    decision=str(cached.decision),
                    confidence=float(cached.confidence),
                    signal_count=int(cached.signal_count),
                    regime=(
                        str(cached.regime)
                        if cached.regime is not None
                        else (
                            detailed.regime
                            if detailed is not None
                            else (
                                str(metrics.market_regime)
                                if metrics is not None and metrics.market_regime is not None
                                else None
                            )
                        )
                    ),
                    created_at=cached.created_at,
                )
            )
        if cached_items:
            items = tuple(sorted(cached_items, key=lambda item: item.timeframe))
        else:
            latest = _latest_market_decisions_subquery()
            rows = self._db.execute(
                select(
                    latest.c.timeframe,
                    latest.c.decision,
                    latest.c.confidence,
                    latest.c.signal_count,
                    latest.c.created_at,
                    CoinMetrics.market_regime,
                    CoinMetrics.market_regime_details,
                )
                .outerjoin(CoinMetrics, CoinMetrics.coin_id == latest.c.coin_id)
                .where(latest.c.coin_id == coin.id, latest.c.market_decision_rank == 1)
                .order_by(latest.c.timeframe.asc())
            ).all()
            items = tuple(
                coin_market_decision_item_read_model_from_mapping(
                    {
                        "timeframe": int(row.timeframe),
                        "decision": str(row.decision),
                        "confidence": float(row.confidence),
                        "signal_count": int(row.signal_count),
                        "regime": (
                            detailed.regime
                            if (detailed := read_regime_details(row.market_regime_details, int(row.timeframe)))
                            is not None
                            else (str(row.market_regime) if row.market_regime is not None else None)
                        ),
                        "created_at": row.created_at,
                    }
                )
                for row in rows
            )
        item = CoinMarketDecisionReadModel(
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            canonical_decision=_canonical_decision(items),
            items=items,
        )
        return coin_market_decision_payload(item)


def list_market_decisions(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    return MarketDecisionCompatibilityQuery(db).list_market_decisions(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


def list_top_market_decisions(db: Session, *, limit: int = 20) -> Sequence[dict[str, Any]]:
    return MarketDecisionCompatibilityQuery(db).list_top_market_decisions(limit=limit)


def get_coin_market_decision(db: Session, symbol: str) -> dict[str, Any] | None:
    return MarketDecisionCompatibilityQuery(db).get_coin_market_decision(symbol)


__all__ = [
    "MarketDecisionCompatibilityQuery",
    "PREFERRED_TIMEFRAMES",
    "_latest_market_decisions_subquery",
    "get_coin_market_decision",
    "list_market_decisions",
    "list_top_market_decisions",
]
