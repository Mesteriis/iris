import itertools
import statistics
from collections.abc import Sequence
from math import sqrt

from src.apps.anomalies.constants import ANOMALY_TYPE_PRICE_VOLUME_DIVERGENCE
from src.apps.anomalies.schemas import AnomalyDetectionContext, DetectorFinding
from src.apps.market_data.candles import CandlePoint


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
    result: list[float] = []
    for previous, current in itertools.pairwise(candles):
        previous_close = float(previous.close)
        result.append((float(current.close) - previous_close) / previous_close if previous_close else 0.0)
    return result


class PriceVolumeDivergenceDetector:
    def __init__(self, *, lookback: int = 48) -> None:
        self._lookback = max(lookback, 24)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        candles = context.candles[-(self._lookback + 1) :]
        volumes = [float(candle.volume) for candle in candles if candle.volume is not None]
        if len(candles) < 12 or len(volumes) < 12:
            return None

        returns = _returns(candles)
        baseline_returns = returns[:-1]
        current_return = returns[-1]
        return_std = _stddev(baseline_returns)
        return_mean = _average(baseline_returns)
        price_z = abs(current_return - return_mean) / return_std if return_std > 0 else 0.0
        price_activation = _scale(price_z, 1.4, 4.5)

        baseline_volumes = volumes[:-1]
        current_volume = volumes[-1]
        volume_mean = _average(baseline_volumes)
        volume_std = _stddev(baseline_volumes)
        volume_z = abs(current_volume - volume_mean) / volume_std if volume_std > 0 else 0.0
        volume_median = statistics.median(baseline_volumes)
        volume_ratio = current_volume / volume_median if volume_median > 0 else 0.0
        volume_activation = max(_scale(volume_z, 1.0, 4.0), _scale(volume_ratio, 1.15, 4.2))

        mode = ""
        if price_activation >= 0.72 and volume_activation <= 0.35:
            mode = "price_led_without_participation"
        elif volume_activation >= 0.72 and price_activation <= 0.35:
            mode = "high_effort_low_result"
        if not mode:
            return None

        imbalance = abs(price_activation - volume_activation)
        quiet_side = 1.0 - min(price_activation, volume_activation)
        activation = max(price_activation, volume_activation)
        divergence_component = (
            (imbalance * 0.55)
            + (quiet_side * 0.20)
            + (activation * 0.25)
        )
        effort_result_ratio = volume_ratio / max(abs(current_return) * 100.0, 0.10)
        price_impact_per_volume = abs(current_return) / max(volume_ratio, 0.10)

        if divergence_component < 0.48:
            return None

        if mode == "price_led_without_participation":
            summary = f"{context.symbol} moved hard without the usual confirming pickup in participation."
            explainability = {
                "what_happened": f"{context.symbol} displaced on price, but volume stayed muted relative to baseline.",
                "unusualness": "Measured as strong price activation paired with weak volume activation.",
                "relative_to": "its own rolling price and volume relationship",
                "relative_to_btc": None,
                "market_wide": False,
            }
            component_scores = {
                "price": _clamp01(divergence_component),
                "volume": _clamp01(divergence_component * 0.78),
            }
        else:
            summary = f"{context.symbol} absorbed abnormal volume without producing the usual proportional price response."
            explainability = {
                "what_happened": f"{context.symbol} traded on abnormal activity, but price barely responded.",
                "unusualness": "Measured as strong volume activation paired with muted price activation.",
                "relative_to": "its own rolling price and volume relationship",
                "relative_to_btc": None,
                "market_wide": False,
            }
            component_scores = {
                "volume": _clamp01(divergence_component),
                "price": _clamp01(divergence_component * 0.60),
            }

        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_PRICE_VOLUME_DIVERGENCE,
            summary=summary,
            component_scores=component_scores,
            metrics={
                "price_return_zscore": float(price_z),
                "volume_zscore": float(volume_z),
                "volume_ratio": float(volume_ratio),
                "effort_result_ratio": float(effort_result_ratio),
                "price_impact_per_volume": float(price_impact_per_volume),
            },
            confidence=_clamp01((divergence_component * 0.74) + (activation * 0.26)),
            explainability=explainability,
        )
