from __future__ import annotations

from collections.abc import Sequence

from src.apps.anomalies.constants import ANOMALY_TYPE_PRICE_SPIKE
from src.apps.anomalies.schemas import AnomalyDetectionContext, DetectorFinding
from src.apps.market_data.repos import CandlePoint


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _average(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance ** 0.5


def _scale(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return _clamp01((value - floor) / (ceiling - floor))


def _returns(candles: Sequence[CandlePoint]) -> list[float]:
    values: list[float] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        previous_close = float(previous.close)
        current_close = float(current.close)
        values.append((current_close - previous_close) / previous_close if previous_close else 0.0)
    return values


def _range_ratios(candles: Sequence[CandlePoint]) -> list[float]:
    ratios: list[float] = []
    for candle in candles:
        close = float(candle.close)
        ratios.append(((float(candle.high) - float(candle.low)) / close) if close else 0.0)
    return ratios


def _true_ranges(candles: Sequence[CandlePoint]) -> list[float]:
    values: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        high = float(candle.high)
        low = float(candle.low)
        if previous_close is None:
            values.append(high - low)
        else:
            values.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = float(candle.close)
    return values


def _percentile_rank(values: Sequence[float], target: float) -> float:
    if not values:
        return 0.0
    less_or_equal = sum(1 for value in values if value <= target)
    return less_or_equal / len(values)


class PriceSpikeDetector:
    def __init__(self, *, lookback: int = 48) -> None:
        self._lookback = max(lookback, 24)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        candles = context.candles[-(self._lookback + 2) :]
        if len(candles) < 12:
            return None

        returns = _returns(candles)
        baseline_returns = returns[:-1]
        current_return = returns[-1]
        return_std = _stddev(baseline_returns)
        return_mean = _average(baseline_returns)
        return_z = abs(current_return - return_mean) / return_std if return_std > 0 else 0.0
        move_percentile = _percentile_rank([abs(value) for value in baseline_returns], abs(current_return))

        range_ratios = _range_ratios(candles)
        baseline_ranges = range_ratios[:-1]
        current_range = range_ratios[-1]
        range_std = _stddev(baseline_ranges)
        range_mean = _average(baseline_ranges)
        range_z = abs(current_range - range_mean) / range_std if range_std > 0 else 0.0

        true_ranges = _true_ranges(candles)
        baseline_atr = _average(true_ranges[:-1][-14:])
        current_true_range = true_ranges[-1]
        atr_ratio = current_true_range / baseline_atr if baseline_atr > 0 else 0.0

        z_component = _scale(return_z, 1.2, 4.4)
        percentile_component = _scale(move_percentile, 0.84, 1.0)
        range_component = _scale(range_z, 1.0, 4.0)
        atr_component = _scale(atr_ratio, 1.2, 3.6)
        price_component = (
            (z_component * 0.40)
            + (percentile_component * 0.25)
            + (range_component * 0.15)
            + (atr_component * 0.20)
        )

        return_direction = "upside" if current_return >= 0 else "downside"
        metric_name = f"return_{context.timeframe}m"
        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_PRICE_SPIKE,
            summary=(
                f"{context.symbol} printed an abnormal {return_direction} price displacement "
                "versus its own rolling return and range history."
            ),
            component_scores={
                "price": _clamp01(price_component),
                "volatility": _clamp01((range_component + atr_component) / 2.0),
            },
            metrics={
                metric_name: float(current_return),
                "return_zscore": float(return_z),
                "move_percentile": float(move_percentile),
                "atr_ratio": float(atr_ratio),
                "range_zscore": float(range_z),
            },
            confidence=_clamp01((price_component * 0.70) + (percentile_component * 0.30)),
            explainability={
                "what_happened": f"{context.symbol} moved unusually fast on the latest closed candle.",
                "unusualness": "Measured against rolling returns, candle range and ATR expansion.",
                "relative_to": "its own rolling price history",
                "relative_to_btc": None,
                "market_wide": False,
            },
        )
