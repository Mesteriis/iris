from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.signal import Signal
from app.models.signal_history import SignalHistory
from app.patterns.semantics import pattern_bias, slug_from_signal_type
from app.services.candles_service import CandlePoint, candle_close_timestamp, fetch_candle_points_between, timeframe_delta
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
    profit_after_24h: float | None
    profit_after_72h: float | None
    maximum_drawdown: float | None
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


def _close_timestamps(candles: Sequence[CandlePoint], timeframe: int) -> list[datetime]:
    return [ensure_utc(candle_close_timestamp(candle.timestamp, timeframe)) for candle in candles]


def _candle_index_map(candles: Sequence[CandlePoint]) -> dict[object, int]:
    return {ensure_utc(candle.timestamp): index for index, candle in enumerate(candles)}


def _index_at_or_after(close_timestamps: Sequence[datetime], target: datetime) -> int | None:
    index = bisect_left(close_timestamps, ensure_utc(target))
    if index >= len(close_timestamps):
        return None
    return index


def _return_for_index(signal: Signal, entry_close: float, candle: CandlePoint) -> float:
    direction = _signal_direction(str(signal.signal_type), float(signal.confidence))
    if direction > 0:
        return (float(candle.close) - entry_close) / max(entry_close, 1e-9)
    return (entry_close - float(candle.close)) / max(entry_close, 1e-9)


def _drawdown_for_window(signal: Signal, entry_close: float, future_window: Sequence[CandlePoint]) -> float | None:
    if not future_window:
        return None
    direction = _signal_direction(str(signal.signal_type), float(signal.confidence))
    if direction > 0:
        return (min(float(item.low) for item in future_window) - entry_close) / max(entry_close, 1e-9)
    return (entry_close - max(float(item.high) for item in future_window)) / max(entry_close, 1e-9)


def _evaluate_signal(
    signal: Signal,
    candles: list[CandlePoint],
    close_timestamps: list[datetime],
    close_index_map: dict[datetime, int],
) -> SignalOutcome:
    signal_close = ensure_utc(signal.candle_timestamp)
    candle_index = close_index_map.get(signal_close)
    if candle_index is None or candle_index >= len(candles):
        return SignalOutcome(
            profit_after_24h=None,
            profit_after_72h=None,
            maximum_drawdown=None,
            result_return=None,
            result_drawdown=None,
            evaluated_at=None,
        )

    entry_close = float(candles[candle_index].close)
    target_24h_index = _index_at_or_after(close_timestamps, signal_close + timedelta(hours=24))
    target_72h_index = _index_at_or_after(close_timestamps, signal_close + timedelta(hours=72))
    profit_after_24h = (
        _return_for_index(signal, entry_close, candles[target_24h_index])
        if target_24h_index is not None and target_24h_index > candle_index
        else None
    )
    profit_after_72h = (
        _return_for_index(signal, entry_close, candles[target_72h_index])
        if target_72h_index is not None and target_72h_index > candle_index
        else None
    )
    window_end_index = target_72h_index or target_24h_index
    future_window = candles[candle_index + 1 : window_end_index + 1] if window_end_index is not None else []
    maximum_drawdown = _drawdown_for_window(signal, entry_close, future_window)
    terminal_return = profit_after_72h if profit_after_72h is not None else profit_after_24h
    return SignalOutcome(
        profit_after_24h=profit_after_24h,
        profit_after_72h=profit_after_72h,
        maximum_drawdown=maximum_drawdown,
        result_return=terminal_return,
        result_drawdown=maximum_drawdown,
        evaluated_at=utc_now() if terminal_return is not None else None,
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
        end = ensure_utc(scoped_signals[-1].candle_timestamp) + timedelta(hours=72) + timeframe_delta(group_timeframe)
        candles = fetch_candle_points_between(db, group_coin_id, group_timeframe, start, end)
        if not candles:
            for signal in scoped_signals:
                rows.append(
                    {
                        "coin_id": signal.coin_id,
                        "timeframe": signal.timeframe,
                        "signal_type": signal.signal_type,
                        "confidence": float(signal.confidence),
                        "market_regime": signal.market_regime,
                        "candle_timestamp": signal.candle_timestamp,
                        "profit_after_24h": None,
                        "profit_after_72h": None,
                        "maximum_drawdown": None,
                        "result_return": None,
                        "result_drawdown": None,
                        "evaluated_at": None,
                    }
                )
            continue

        close_timestamps = _close_timestamps(candles, group_timeframe)
        close_index_map = {timestamp: index for index, timestamp in enumerate(close_timestamps)}
        for signal in scoped_signals:
            outcome = _evaluate_signal(signal, candles, close_timestamps, close_index_map)
            if outcome.evaluated_at is not None:
                evaluated += 1
            rows.append(
                {
                    "coin_id": signal.coin_id,
                    "timeframe": signal.timeframe,
                    "signal_type": signal.signal_type,
                    "confidence": float(signal.confidence),
                    "market_regime": signal.market_regime,
                    "candle_timestamp": signal.candle_timestamp,
                    "profit_after_24h": outcome.profit_after_24h,
                    "profit_after_72h": outcome.profit_after_72h,
                    "maximum_drawdown": outcome.maximum_drawdown,
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
                "market_regime": stmt.excluded.market_regime,
                "profit_after_24h": stmt.excluded.profit_after_24h,
                "profit_after_72h": stmt.excluded.profit_after_72h,
                "maximum_drawdown": stmt.excluded.maximum_drawdown,
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
