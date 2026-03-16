from datetime import UTC, datetime, timedelta, timezone

from src.apps.predictions.engines import PredictionWindowCandleInput, PredictionWindowInput, evaluate_prediction_window


def _candle(*, minutes: int, high: float, low: float, close: float) -> PredictionWindowCandleInput:
    start = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
    return PredictionWindowCandleInput(
        timestamp=start + timedelta(minutes=minutes),
        high=high,
        low=low,
        close=close,
    )


def test_prediction_window_engine_confirms_up_move() -> None:
    deadline = datetime(2026, 3, 14, 14, 0, tzinfo=UTC)
    result = evaluate_prediction_window(
        PredictionWindowInput(
            expected_move="up",
            deadline=deadline,
            now=deadline,
            candles=(
                _candle(minutes=0, high=100.0, low=99.0, close=100.0),
                _candle(minutes=15, high=102.0, low=100.5, close=101.4),
            ),
        )
    )

    assert result is not None
    assert result.status == "confirmed"
    assert result.success is True
    assert result.actual_move > 0.015


def test_prediction_window_engine_marks_up_move_as_failed_after_deadline() -> None:
    deadline = datetime(2026, 3, 14, 14, 0, tzinfo=UTC)
    result = evaluate_prediction_window(
        PredictionWindowInput(
            expected_move="up",
            deadline=deadline,
            now=deadline,
            candles=(
                _candle(minutes=0, high=100.0, low=99.5, close=100.0),
                _candle(minutes=15, high=99.2, low=97.8, close=98.2),
            ),
        )
    )

    assert result is not None
    assert result.status == "failed"
    assert result.success is False
    assert result.profit < 0


def test_prediction_window_engine_marks_down_move_as_expired_when_threshold_not_hit() -> None:
    deadline = datetime(2026, 3, 14, 14, 0, tzinfo=UTC)
    result = evaluate_prediction_window(
        PredictionWindowInput(
            expected_move="down",
            deadline=deadline,
            now=deadline,
            candles=(
                _candle(minutes=0, high=100.0, low=99.5, close=100.0),
                _candle(minutes=15, high=100.6, low=99.7, close=100.2),
            ),
        )
    )

    assert result is not None
    assert result.status == "expired"
    assert result.success is False
