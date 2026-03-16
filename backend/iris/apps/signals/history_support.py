from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from iris.apps.market_data.candles import CandlePoint, candle_close_timestamp, timeframe_delta
from iris.apps.market_data.domain import ensure_utc, utc_now
from iris.apps.patterns.domain.semantics import pattern_bias, slug_from_signal_type

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
    evaluated_at: datetime | None


class _DirectionalSignal(Protocol):
    @property
    def signal_type(self) -> str: ...

    @property
    def confidence(self) -> float: ...


class _HistoricalSignal(_DirectionalSignal, Protocol):
    @property
    def candle_timestamp(self) -> datetime: ...

    @property
    def timeframe(self) -> int: ...


def _signal_direction(signal_type: str, confidence: float) -> int:
    slug = slug_from_signal_type(signal_type)
    if slug is not None:
        return pattern_bias(slug, fallback_price_delta=confidence - 0.5)
    if signal_type in _BULLISH_SIGNAL_TYPES:
        return 1
    if signal_type in _BEARISH_SIGNAL_TYPES:
        return -1
    return 1 if confidence >= 0.5 else -1


def _open_timestamp_from_signal(signal: _HistoricalSignal) -> datetime:
    return ensure_utc(signal.candle_timestamp) - timeframe_delta(signal.timeframe)


def _close_timestamps(candles: Sequence[CandlePoint], timeframe: int) -> list[datetime]:
    return [ensure_utc(candle_close_timestamp(candle.timestamp, timeframe)) for candle in candles]


def _candle_index_map(candles: Sequence[CandlePoint]) -> dict[datetime, int]:
    return {ensure_utc(candle.timestamp): index for index, candle in enumerate(candles)}


def _index_at_or_after(close_timestamps: Sequence[datetime], target: datetime) -> int | None:
    index = bisect_left(close_timestamps, ensure_utc(target))
    if index >= len(close_timestamps):
        return None
    return index


def _return_for_index(signal: _DirectionalSignal, entry_close: float, candle: CandlePoint) -> float:
    direction = _signal_direction(str(signal.signal_type), float(signal.confidence))
    if direction > 0:
        return (float(candle.close) - entry_close) / max(entry_close, 1e-9)
    return (entry_close - float(candle.close)) / max(entry_close, 1e-9)


def _drawdown_for_window(
    signal: _DirectionalSignal,
    entry_close: float,
    future_window: Sequence[CandlePoint],
) -> float | None:
    if not future_window:
        return None
    direction = _signal_direction(str(signal.signal_type), float(signal.confidence))
    if direction > 0:
        return (min(float(item.low) for item in future_window) - entry_close) / max(entry_close, 1e-9)
    return (entry_close - max(float(item.high) for item in future_window)) / max(entry_close, 1e-9)


def _evaluate_signal(
    signal: _HistoricalSignal,
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


__all__ = [
    "SIGNAL_EVALUATION_HORIZON_BARS",
    "SIGNAL_HISTORY_LOOKBACK_DAYS",
    "SIGNAL_HISTORY_RECENT_LIMIT",
    "SignalOutcome",
    "_candle_index_map",
    "_close_timestamps",
    "_drawdown_for_window",
    "_evaluate_signal",
    "_index_at_or_after",
    "_open_timestamp_from_signal",
    "_return_for_index",
    "_signal_direction",
]
