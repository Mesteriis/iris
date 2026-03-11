from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.signal import Signal
from app.models.signal_history import SignalHistory
from app.patterns.semantics import pattern_bias, slug_from_signal_type
from app.services.candles_service import CandlePoint, fetch_candle_points_between, timeframe_delta
from app.services.market_data import ensure_utc, utc_now

SIGNAL_HISTORY_LOOKBACK_DAYS = 365
SIGNAL_HISTORY_RECENT_LIMIT = 512
SIGNAL_EVALUATION_HORIZON_BARS = {
    15: 16,
    60: 12,
    240: 8,
    1440: 5,
}

_BULLISH_SIGNAL_TYPES = {
    "golden_cross",
    "bullish_breakout",
    "rsi_oversold",
}
_BEARISH_SIGNAL_TYPES = {
    "death_cross",
    "bearish_breakdown",
    "rsi_overbought",
}


@dataclass(slots=True, frozen=True)
class SignalOutcome:
    result_return: float | None
    result_drawdown: float | None
    evaluated_at: object | None


def _signal_direction(signal_type: str, confidence: float) -> int:
    slug = slug_from_signal_type(signal_type)
    if slug is not None:
        return pattern_bias(slug, fallback_price_delta=confidence - 0.5)
    if signal_type in _BULLISH_SIGNAL_TYPES:
        return 1
    if signal_type in _BEARISH_SIGNAL_TYPES:
        return -1
    return 1 if confidence >= 0.5 else -1


def _open_timestamp_from_signal(signal: Signal) -> object:
    return ensure_utc(signal.candle_timestamp) - timeframe_delta(signal.timeframe)


def _candle_index_map(candles: Sequence[CandlePoint]) -> dict[object, int]:
    return {ensure_utc(candle.timestamp): index for index, candle in enumerate(candles)}


def _evaluate_signal(signal: Signal, candles: list[CandlePoint], index_map: dict[object, int]) -> SignalOutcome:
    open_timestamp = _open_timestamp_from_signal(signal)
    candle_index = index_map.get(open_timestamp)
    if candle_index is None or candle_index >= len(candles):
        return SignalOutcome(result_return=None, result_drawdown=None, evaluated_at=None)
    horizon = SIGNAL_EVALUATION_HORIZON_BARS.get(signal.timeframe, 8)
    future_window = candles[candle_index + 1 : candle_index + 1 + horizon]
    if len(future_window) < horizon:
        return SignalOutcome(result_return=None, result_drawdown=None, evaluated_at=None)

    entry_close = float(candles[candle_index].close)
    last_close = float(future_window[-1].close)
    direction = _signal_direction(str(signal.signal_type), float(signal.confidence))
    if direction > 0:
        terminal_return = (last_close - entry_close) / max(entry_close, 1e-9)
        drawdown = (min(float(item.low) for item in future_window) - entry_close) / max(entry_close, 1e-9)
    else:
        terminal_return = (entry_close - last_close) / max(entry_close, 1e-9)
        drawdown = (entry_close - max(float(item.high) for item in future_window)) / max(entry_close, 1e-9)
    return SignalOutcome(
        result_return=terminal_return,
        result_drawdown=drawdown,
        evaluated_at=utc_now(),
    )


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


def refresh_signal_history(
    db: Session,
    *,
    lookback_days: int = SIGNAL_HISTORY_LOOKBACK_DAYS,
    coin_id: int | None = None,
    timeframe: int | None = None,
    limit_per_scope: int | None = None,
    commit: bool = True,
) -> dict[str, object]:
    signals = _fetch_signals(
        db,
        lookback_days=lookback_days,
        coin_id=coin_id,
        timeframe=timeframe,
        limit_per_scope=limit_per_scope,
    )
    if not signals:
        return {
            "status": "ok",
            "rows": 0,
            "evaluated": 0,
            "coin_id": coin_id,
            "timeframe": timeframe,
        }

    groups: dict[tuple[int, int], list[Signal]] = defaultdict(list)
    for signal in signals:
        groups[(signal.coin_id, signal.timeframe)].append(signal)

    rows: list[dict[str, object]] = []
    evaluated = 0
    for (group_coin_id, group_timeframe), scoped_signals in groups.items():
        if not scoped_signals:
            continue
        start = _open_timestamp_from_signal(scoped_signals[0])
        horizon = SIGNAL_EVALUATION_HORIZON_BARS.get(group_timeframe, 8)
        end = ensure_utc(scoped_signals[-1].candle_timestamp) + timeframe_delta(group_timeframe) * (horizon + 1)
        candles = fetch_candle_points_between(db, group_coin_id, group_timeframe, start, end)
        if not candles:
            for signal in scoped_signals:
                rows.append(
                    {
                        "coin_id": signal.coin_id,
                        "timeframe": signal.timeframe,
                        "signal_type": signal.signal_type,
                        "confidence": float(signal.confidence),
                        "candle_timestamp": signal.candle_timestamp,
                        "result_return": None,
                        "result_drawdown": None,
                        "evaluated_at": None,
                    }
                )
            continue

        index_map = _candle_index_map(candles)
        for signal in scoped_signals:
            outcome = _evaluate_signal(signal, candles, index_map)
            if outcome.evaluated_at is not None:
                evaluated += 1
            rows.append(
                {
                    "coin_id": signal.coin_id,
                    "timeframe": signal.timeframe,
                    "signal_type": signal.signal_type,
                    "confidence": float(signal.confidence),
                    "candle_timestamp": signal.candle_timestamp,
                    "result_return": outcome.result_return,
                    "result_drawdown": outcome.result_drawdown,
                    "evaluated_at": outcome.evaluated_at,
                }
            )

    if rows:
        stmt = insert(SignalHistory).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe", "signal_type", "candle_timestamp"],
            set_={
                "confidence": stmt.excluded.confidence,
                "result_return": stmt.excluded.result_return,
                "result_drawdown": stmt.excluded.result_drawdown,
                "evaluated_at": stmt.excluded.evaluated_at,
            },
        )
        db.execute(stmt)
    if commit:
        db.commit()
    return {
        "status": "ok",
        "rows": len(rows),
        "evaluated": evaluated,
        "coin_id": coin_id,
        "timeframe": timeframe,
    }


def refresh_recent_signal_history(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    commit: bool = True,
) -> dict[str, object]:
    return refresh_signal_history(
        db,
        lookback_days=SIGNAL_HISTORY_LOOKBACK_DAYS,
        coin_id=coin_id,
        timeframe=timeframe,
        limit_per_scope=SIGNAL_HISTORY_RECENT_LIMIT,
        commit=commit,
    )
