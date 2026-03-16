import itertools
from collections.abc import Sequence
from math import sqrt

from iris.apps.anomalies.constants import ANOMALY_TYPE_COMPRESSION_EXPANSION
from iris.apps.anomalies.schemas import AnomalyDetectionContext, DetectorFinding
from iris.apps.market_data.candles import CandlePoint


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _average(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return sqrt(variance)


def _scale(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return _clamp01((value - floor) / (ceiling - floor))


def _returns(candles: Sequence[CandlePoint]) -> list[float]:
    values: list[float] = []
    for previous, current in itertools.pairwise(candles):
        previous_close = float(previous.close)
        values.append((float(current.close) - previous_close) / previous_close if previous_close else 0.0)
    return values


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


def _rolling_std(values: Sequence[float], window: int) -> list[float]:
    if len(values) < window:
        return []
    return [_stddev(values[index - window : index]) for index in range(window, len(values) + 1)]


def _percentile_rank(values: Sequence[float], target: float) -> float:
    if not values:
        return 0.0
    less_or_equal = sum(1 for value in values if value <= target)
    return less_or_equal / len(values)


class CompressionExpansionDetector:
    def __init__(self, *, lookback: int = 48, compression_window: int = 8) -> None:
        self._lookback = max(lookback, 28)
        self._compression_window = max(compression_window, 6)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        candles = context.candles[-(self._lookback + 2) :]
        if len(candles) < self._compression_window + 18:
            return None

        returns = _returns(candles)
        baseline_returns = returns[:-1]
        compressed_returns = baseline_returns[-self._compression_window :]
        earlier_returns = baseline_returns[:-self._compression_window][-24:]
        if len(compressed_returns) < self._compression_window or len(earlier_returns) < 12:
            return None

        rolling_stds = _rolling_std(baseline_returns, self._compression_window)
        compressed_vol = _stddev(compressed_returns)
        baseline_vol = _stddev(earlier_returns)
        compression_ratio = compressed_vol / baseline_vol if baseline_vol > 0 else 0.0
        squeeze_percentile = _percentile_rank(rolling_stds[:-1], compressed_vol) if len(rolling_stds) > 1 else 0.0

        true_ranges = _true_ranges(candles)
        compressed_atr = _average(true_ranges[:-1][-self._compression_window :])
        baseline_atr = _average(true_ranges[:-1][-(self._compression_window + 14) : -self._compression_window])
        current_true_range = true_ranges[-1]
        range_expansion_ratio = current_true_range / compressed_atr if compressed_atr > 0 else 0.0
        atr_expansion = current_true_range / baseline_atr if baseline_atr > 0 else 0.0
        current_return = abs(returns[-1]) if returns else 0.0
        realized_jump_ratio = current_return / compressed_vol if compressed_vol > 0 else 0.0

        compression_component = _scale(1.0 - compression_ratio, 0.10, 0.85)
        squeeze_component = _scale(1.0 - squeeze_percentile, 0.45, 1.0)
        expansion_component = _scale(range_expansion_ratio, 1.2, 4.0)
        realized_component = _scale(realized_jump_ratio, 1.0, 5.5)
        volatility_component = (
            (compression_component * 0.25)
            + (squeeze_component * 0.15)
            + (expansion_component * 0.35)
            + (realized_component * 0.25)
        )
        if compression_ratio > 0.95 or range_expansion_ratio < 1.4 or volatility_component < 0.44:
            return None

        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_COMPRESSION_EXPANSION,
            summary=f"{context.symbol} broke out of a compressed volatility pocket into an expanded range state.",
            component_scores={
                "volatility": _clamp01(volatility_component),
                "price": _clamp01((expansion_component * 0.55) + (realized_component * 0.45)),
            },
            metrics={
                "compression_ratio": float(compression_ratio),
                "squeeze_percentile": float(squeeze_percentile),
                "range_expansion_ratio": float(range_expansion_ratio),
                "atr_expansion": float(atr_expansion),
                "realized_jump_ratio": float(realized_jump_ratio),
            },
            confidence=_clamp01((volatility_component * 0.72) + (compression_component * 0.28)),
            explainability={
                "what_happened": f"{context.symbol} transitioned from volatility compression into an abrupt expansion.",
                "unusualness": "Measured via squeeze percentile, compression ratio, ATR expansion and jump intensity.",
                "relative_to": "its own compressed volatility baseline",
                "relative_to_btc": None,
                "market_wide": False,
            },
        )
