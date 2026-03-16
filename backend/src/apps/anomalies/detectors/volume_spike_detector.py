import statistics
from collections.abc import Sequence

from src.apps.anomalies.constants import ANOMALY_TYPE_VOLUME_SPIKE
from src.apps.anomalies.schemas import AnomalyDetectionContext, DetectorFinding


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


def _percentile_rank(values: Sequence[float], target: float) -> float:
    if not values:
        return 0.0
    less_or_equal = sum(1 for value in values if value <= target)
    return less_or_equal / len(values)


class VolumeSpikeDetector:
    def __init__(self, *, lookback: int = 48) -> None:
        self._lookback = max(lookback, 24)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        volumes = [
            float(candle.volume)
            for candle in context.candles[-(self._lookback + 1) :]
            if candle.volume is not None
        ]
        if len(volumes) < 12:
            return None

        baseline = volumes[:-1]
        current_volume = volumes[-1]
        volume_mean = _average(baseline)
        volume_std = _stddev(baseline)
        volume_z = abs(current_volume - volume_mean) / volume_std if volume_std > 0 else 0.0
        volume_median = statistics.median(baseline)
        volume_ratio = current_volume / volume_median if volume_median > 0 else 0.0
        volume_percentile = _percentile_rank(baseline, current_volume)

        z_component = _scale(volume_z, 1.0, 4.0)
        ratio_component = _scale(volume_ratio, 1.2, 4.5)
        percentile_component = _scale(volume_percentile, 0.85, 1.0)
        volume_component = (z_component * 0.42) + (ratio_component * 0.36) + (percentile_component * 0.22)

        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_VOLUME_SPIKE,
            summary=f"{context.symbol} traded on materially abnormal participation versus its rolling volume baseline.",
            component_scores={"volume": _clamp01(volume_component)},
            metrics={
                "volume_zscore": float(volume_z),
                "volume_ratio": float(volume_ratio),
                "volume_percentile": float(volume_percentile),
            },
            confidence=_clamp01((volume_component * 0.75) + (ratio_component * 0.25)),
            explainability={
                "what_happened": f"{context.symbol} printed a volume surge on the last candle.",
                "unusualness": "Measured against rolling mean, median ratio and percentile rank.",
                "relative_to": "its own rolling volume history",
                "relative_to_btc": None,
                "market_wide": False,
            },
        )
