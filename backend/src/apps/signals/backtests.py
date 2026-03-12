from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Coin
from src.apps.market_data.service_layer import get_coin_by_symbol
from src.apps.signals.backtest_support import (
    BacktestPoint as _BacktestPoint,
    clamp_backtest_value as _clamp,
    serialize_backtest_group as _serialize_group,
    sharpe_ratio as _sharpe_ratio,
)
from src.apps.signals.models import SignalHistory
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value

BACKTEST_LOOKBACK_DAYS = 365


class SignalBacktestCompatibilityQuery:
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
                    "component": "SignalBacktestCompatibilityQuery",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def _query_points(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        signal_type: str | None = None,
        lookback_days: int = BACKTEST_LOOKBACK_DAYS,
    ) -> list[_BacktestPoint]:
        cutoff = utc_now() - timedelta(days=lookback_days)
        stmt = (
            select(
                Coin.symbol,
                SignalHistory.signal_type,
                SignalHistory.timeframe,
                SignalHistory.confidence,
                SignalHistory.result_return,
                SignalHistory.result_drawdown,
                SignalHistory.evaluated_at,
            )
            .join(Coin, Coin.id == SignalHistory.coin_id)
            .where(
                Coin.deleted_at.is_(None),
                SignalHistory.candle_timestamp >= cutoff,
                SignalHistory.result_return.is_not(None),
                SignalHistory.result_drawdown.is_not(None),
            )
        )
        if symbol is not None:
            stmt = stmt.where(Coin.symbol == symbol.upper())
        if timeframe is not None:
            stmt = stmt.where(SignalHistory.timeframe == timeframe)
        if signal_type is not None:
            stmt = stmt.where(SignalHistory.signal_type == signal_type)
        rows = self._db.execute(stmt).all()
        return [
            _BacktestPoint(
                symbol=str(row.symbol),
                signal_type=str(row.signal_type),
                timeframe=int(row.timeframe),
                confidence=float(row.confidence),
                result_return=float(row.result_return),
                result_drawdown=float(row.result_drawdown),
                evaluated_at=row.evaluated_at,
            )
            for row in rows
        ]

    def list_backtests(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        signal_type: str | None = None,
        lookback_days: int = BACKTEST_LOOKBACK_DAYS,
        limit: int = 100,
    ) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_backtests.deprecated",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            lookback_days=lookback_days,
            limit=limit,
        )
        points = self._query_points(
            symbol=symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            lookback_days=lookback_days,
        )
        grouped: dict[tuple[str, int], list[_BacktestPoint]] = defaultdict(list)
        for point in points:
            grouped[(point.signal_type, point.timeframe)].append(point)
        rows = [
            _serialize_group(
                symbol=symbol.upper() if symbol is not None else None,
                signal_type=group_signal_type,
                timeframe=group_timeframe,
                points=group_points,
            )
            for (group_signal_type, group_timeframe), group_points in grouped.items()
        ]
        rows.sort(
            key=lambda row: (
                row["sample_size"],
                row["sharpe_ratio"],
                row["roi"],
                row["win_rate"],
            ),
            reverse=True,
        )
        return rows[: max(limit, 1)]

    def list_top_backtests(
        self,
        *,
        timeframe: int | None = None,
        lookback_days: int = BACKTEST_LOOKBACK_DAYS,
        limit: int = 20,
    ) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_top_backtests.deprecated",
            mode="read",
            timeframe=timeframe,
            lookback_days=lookback_days,
            limit=limit,
        )
        rows = self.list_backtests(
            timeframe=timeframe,
            lookback_days=lookback_days,
            limit=max(limit * 4, 50),
        )
        sorted_rows = list(rows)
        sorted_rows.sort(
            key=lambda row: (
                row["sharpe_ratio"],
                row["roi"],
                row["win_rate"],
                row["sample_size"],
            ),
            reverse=True,
        )
        return sorted_rows[: max(limit, 1)]

    def get_coin_backtests(
        self,
        symbol: str,
        *,
        timeframe: int | None = None,
        signal_type: str | None = None,
        lookback_days: int = BACKTEST_LOOKBACK_DAYS,
        limit: int = 50,
    ) -> dict[str, Any] | None:
        normalized_symbol = symbol.strip().upper()
        self._log(
            logging.WARNING,
            "compat.get_coin_backtests.deprecated",
            mode="read",
            symbol=normalized_symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            lookback_days=lookback_days,
            limit=limit,
        )
        coin = get_coin_by_symbol(self._db, normalized_symbol)
        if coin is None:
            return None
        return {
            "coin_id": coin.id,
            "symbol": coin.symbol,
            "items": list(
                self.list_backtests(
                    symbol=coin.symbol,
                    timeframe=timeframe,
                    signal_type=signal_type,
                    lookback_days=lookback_days,
                    limit=limit,
                )
            ),
        }


def list_backtests(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    signal_type: str | None = None,
    lookback_days: int = BACKTEST_LOOKBACK_DAYS,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    return SignalBacktestCompatibilityQuery(db).list_backtests(
        symbol=symbol,
        timeframe=timeframe,
        signal_type=signal_type,
        lookback_days=lookback_days,
        limit=limit,
    )


def list_top_backtests(
    db: Session,
    *,
    timeframe: int | None = None,
    lookback_days: int = BACKTEST_LOOKBACK_DAYS,
    limit: int = 20,
) -> Sequence[dict[str, Any]]:
    return SignalBacktestCompatibilityQuery(db).list_top_backtests(
        timeframe=timeframe,
        lookback_days=lookback_days,
        limit=limit,
    )


def get_coin_backtests(
    db: Session,
    symbol: str,
    *,
    timeframe: int | None = None,
    signal_type: str | None = None,
    lookback_days: int = BACKTEST_LOOKBACK_DAYS,
    limit: int = 50,
) -> dict[str, Any] | None:
    return SignalBacktestCompatibilityQuery(db).get_coin_backtests(
        symbol=symbol,
        timeframe=timeframe,
        signal_type=signal_type,
        lookback_days=lookback_days,
        limit=limit,
    )


__all__ = [
    "BACKTEST_LOOKBACK_DAYS",
    "SignalBacktestCompatibilityQuery",
    "_BacktestPoint",
    "_clamp",
    "_serialize_group",
    "_sharpe_ratio",
    "get_coin_backtests",
    "list_backtests",
    "list_top_backtests",
]
