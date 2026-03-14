from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.apps.signals.engines import (
    SignalHistoryCandleInput,
    SignalHistorySignalInput,
    evaluate_signal_history_batch,
)


def test_signal_history_engine_uses_explicit_evaluation_clock() -> None:
    start = datetime(2026, 3, 11, 0, 0, tzinfo=UTC)
    result = evaluate_signal_history_batch(
        signals=(
            SignalHistorySignalInput(
                coin_id=1,
                timeframe=60,
                signal_type="golden_cross",
                confidence=0.8,
                market_regime="bull_trend",
                candle_timestamp=start + timedelta(hours=1),
            ),
        ),
        candles=tuple(
            SignalHistoryCandleInput(
                timestamp=start + timedelta(hours=index),
                open=100.0 + index,
                high=102.0 + index,
                low=100.0 + index,
                close=100.0 + index,
                volume=1_000.0 + index,
            )
            for index in range(80)
        ),
        evaluated_at=start + timedelta(days=3),
    )

    assert result[0].profit_after_24h == 0.24
    assert result[0].profit_after_72h == 0.72
    assert result[0].evaluated_at == start + timedelta(days=3)


def test_signal_history_engine_returns_empty_metrics_for_missing_candles() -> None:
    start = datetime(2026, 3, 11, 0, 0, tzinfo=UTC)
    result = evaluate_signal_history_batch(
        signals=(
            SignalHistorySignalInput(
                coin_id=1,
                timeframe=60,
                signal_type="golden_cross",
                confidence=0.8,
                market_regime="bull_trend",
                candle_timestamp=start + timedelta(hours=1),
            ),
        ),
        candles=(),
        evaluated_at=start + timedelta(days=3),
    )

    assert result[0].result_return is None
    assert result[0].evaluated_at is None
