from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.apps.market_data.domain import utc_now
from src.apps.signals.history_support import (
    SIGNAL_HISTORY_LOOKBACK_DAYS,
    _candle_index_map,
    _close_timestamps,
    _drawdown_for_window,
    _evaluate_signal,
    _index_at_or_after,
    _open_timestamp_from_signal,
    _return_for_index,
    _signal_direction,
)
from src.apps.signals.models import Signal


def _fetch_signals(
    db: Session,
    *,
    lookback_days: int,
    coin_id: int | None = None,
    timeframe: int | None = None,
    limit_per_scope: int | None = None,
) -> list[Signal]:
    cutoff = utc_now() - timedelta(days=lookback_days)
    stmt = (
        select(Signal)
        .where(Signal.candle_timestamp >= cutoff)
        .order_by(Signal.coin_id.asc(), Signal.timeframe.asc(), Signal.candle_timestamp.asc(), Signal.created_at.asc())
    )
    if coin_id is not None:
        stmt = stmt.where(Signal.coin_id == coin_id)
    if timeframe is not None:
        stmt = stmt.where(Signal.timeframe == timeframe)
    rows = db.scalars(stmt).all()
    if limit_per_scope is None:
        return rows
    grouped: dict[tuple[int, int], list[Signal]] = defaultdict(list)
    for row in rows:
        grouped[(row.coin_id, row.timeframe)].append(row)
    limited: list[Signal] = []
    for scoped_rows in grouped.values():
        limited.extend(scoped_rows[-limit_per_scope:])
    limited.sort(key=lambda row: (row.coin_id, row.timeframe, row.candle_timestamp, row.created_at))
    return limited


__all__ = [
    "_candle_index_map",
    "_close_timestamps",
    "_drawdown_for_window",
    "_evaluate_signal",
    "_fetch_signals",
    "_index_at_or_after",
    "_open_timestamp_from_signal",
    "_return_for_index",
    "_signal_direction",
]
