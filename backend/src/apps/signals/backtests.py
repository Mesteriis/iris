from __future__ import annotations

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

BACKTEST_LOOKBACK_DAYS = 365


def _query_points(
    db: Session,
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
    rows = db.execute(stmt).all()
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
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    signal_type: str | None = None,
    lookback_days: int = BACKTEST_LOOKBACK_DAYS,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    points = _query_points(
        db,
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
    db: Session,
    *,
    timeframe: int | None = None,
    lookback_days: int = BACKTEST_LOOKBACK_DAYS,
    limit: int = 20,
) -> Sequence[dict[str, Any]]:
    rows = list_backtests(
        db,
        timeframe=timeframe,
        lookback_days=lookback_days,
        limit=max(limit * 4, 50),
    )
    rows.sort(
        key=lambda row: (
            row["sharpe_ratio"],
            row["roi"],
            row["win_rate"],
            row["sample_size"],
        ),
        reverse=True,
    )
    return rows[: max(limit, 1)]


def get_coin_backtests(
    db: Session,
    symbol: str,
    *,
    timeframe: int | None = None,
    signal_type: str | None = None,
    lookback_days: int = BACKTEST_LOOKBACK_DAYS,
    limit: int = 50,
) -> dict[str, Any] | None:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        return None
    return {
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "items": list(
            list_backtests(
                db,
                symbol=coin.symbol,
                timeframe=timeframe,
                signal_type=signal_type,
                lookback_days=lookback_days,
                limit=limit,
            )
        ),
    }
