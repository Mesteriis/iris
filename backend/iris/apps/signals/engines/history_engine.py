from datetime import datetime, timedelta

from iris.apps.market_data.candles import CandlePoint
from iris.apps.market_data.domain import ensure_utc
from iris.apps.signals.engines.contracts import (
    SignalHistoryCandleInput,
    SignalHistoryEvaluation,
    SignalHistorySignalInput,
)
from iris.apps.signals.history_support import (
    _close_timestamps,
    _drawdown_for_window,
    _index_at_or_after,
    _return_for_index,
)


def evaluate_signal_history_batch(
    *,
    signals: tuple[SignalHistorySignalInput, ...],
    candles: tuple[SignalHistoryCandleInput, ...],
    evaluated_at: datetime,
) -> tuple[SignalHistoryEvaluation, ...]:
    candle_points = [
        CandlePoint(
            timestamp=candle.timestamp,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )
        for candle in candles
    ]
    if not signals:
        return ()
    if not candle_points:
        return tuple(_empty_evaluation(signal) for signal in signals)

    close_timestamps = _close_timestamps(candle_points, signals[0].timeframe)
    close_index_map = {timestamp: index for index, timestamp in enumerate(close_timestamps)}
    normalized_evaluated_at = ensure_utc(evaluated_at)
    return tuple(
        _evaluate_signal_history(
            signal=signal,
            candles=candle_points,
            close_timestamps=close_timestamps,
            close_index_map=close_index_map,
            evaluated_at=normalized_evaluated_at,
        )
        for signal in signals
    )


def _evaluate_signal_history(
    *,
    signal: SignalHistorySignalInput,
    candles: list[CandlePoint],
    close_timestamps: list[datetime],
    close_index_map: dict[datetime, int],
    evaluated_at: datetime,
) -> SignalHistoryEvaluation:
    signal_close = ensure_utc(signal.candle_timestamp)
    candle_index = close_index_map.get(signal_close)
    if candle_index is None or candle_index >= len(candles):
        return _empty_evaluation(signal)

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
    return SignalHistoryEvaluation(
        coin_id=signal.coin_id,
        timeframe=signal.timeframe,
        signal_type=signal.signal_type,
        confidence=signal.confidence,
        market_regime=signal.market_regime,
        candle_timestamp=signal.candle_timestamp,
        profit_after_24h=profit_after_24h,
        profit_after_72h=profit_after_72h,
        maximum_drawdown=maximum_drawdown,
        result_return=terminal_return,
        result_drawdown=maximum_drawdown,
        evaluated_at=evaluated_at if terminal_return is not None else None,
    )


def _empty_evaluation(signal: SignalHistorySignalInput) -> SignalHistoryEvaluation:
    return SignalHistoryEvaluation(
        coin_id=signal.coin_id,
        timeframe=signal.timeframe,
        signal_type=signal.signal_type,
        confidence=signal.confidence,
        market_regime=signal.market_regime,
        candle_timestamp=signal.candle_timestamp,
        profit_after_24h=None,
        profit_after_72h=None,
        maximum_drawdown=None,
        result_return=None,
        result_drawdown=None,
        evaluated_at=None,
    )


__all__ = ["evaluate_signal_history_batch"]
