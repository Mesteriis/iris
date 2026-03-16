from iris.apps.predictions.engines.contracts import PredictionWindowInput
from iris.apps.predictions.support import PREDICTION_MOVE_THRESHOLD, PredictionOutcome


def evaluate_prediction_window(window: PredictionWindowInput) -> PredictionOutcome | None:
    if len(window.candles) < 2:
        return None

    entry_price = float(window.candles[0].close)
    closes = [float(item.close) for item in window.candles]
    highs = [float(item.high) for item in window.candles]
    lows = [float(item.low) for item in window.candles]
    max_move = (max(highs) - entry_price) / entry_price if entry_price else 0.0
    min_move = (min(lows) - entry_price) / entry_price if entry_price else 0.0
    last_move = (closes[-1] - entry_price) / entry_price if entry_price else 0.0

    if window.expected_move == "up":
        if max_move >= PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="confirmed", actual_move=max_move, success=True, profit=max_move)
        if window.now >= window.deadline and last_move <= -PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="failed", actual_move=last_move, success=False, profit=last_move)
        if window.now >= window.deadline:
            return PredictionOutcome(status="expired", actual_move=last_move, success=False, profit=last_move)
        return None

    bearish_move = abs(min_move)
    if bearish_move >= PREDICTION_MOVE_THRESHOLD:
        return PredictionOutcome(status="confirmed", actual_move=min_move, success=True, profit=bearish_move)
    if window.now >= window.deadline and last_move >= PREDICTION_MOVE_THRESHOLD:
        return PredictionOutcome(status="failed", actual_move=last_move, success=False, profit=-last_move)
    if window.now >= window.deadline:
        return PredictionOutcome(
            status="expired",
            actual_move=last_move,
            success=False,
            profit=-max(last_move, 0.0),
        )
    return None


__all__ = ["evaluate_prediction_window"]
