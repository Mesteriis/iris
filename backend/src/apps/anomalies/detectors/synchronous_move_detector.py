from __future__ import annotations

from collections.abc import Sequence

from src.apps.anomalies.constants import ANOMALY_SCOPE_SECTOR, ANOMALY_TYPE_CROSS_ASSET_SYNCHRONOUS_MOVE
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
    return variance ** 0.5


def _returns(candles: Sequence[CandlePoint]) -> list[float]:
    values: list[float] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        previous_close = float(previous.close)
        values.append((float(current.close) - previous_close) / previous_close if previous_close else 0.0)
    return values


def _scale(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return _clamp01((value - floor) / (ceiling - floor))


class SynchronousMoveDetector:
    def __init__(self, *, lookback: int = 48) -> None:
        self._lookback = max(lookback, 24)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        if not context.sector_peer_candles:
            return None

        movers: list[tuple[str, float, float]] = []
        peer_count = 0
        peer_signs: list[int] = []
        for symbol, candles in context.sector_peer_candles.items():
            returns = _returns(candles[-(self._lookback + 2) :])
            if len(returns) < 12:
                continue
            peer_count += 1
            baseline = returns[:-1]
            latest = returns[-1]
            baseline_std = _stddev(baseline)
            baseline_mean = _average(baseline)
            zscore = abs(latest - baseline_mean) / baseline_std if baseline_std > 0 else 0.0
            peer_signs.append(1 if latest >= 0 else -1)
            if zscore >= 1.5:
                movers.append((symbol, latest, zscore))

        if peer_count < 2:
            return None

        trigger_returns = _returns(context.candles[-(self._lookback + 2) :])
        trigger_return = trigger_returns[-1] if trigger_returns else 0.0
        mover_signs = [1 if value >= 0 else -1 for _, value, _ in movers]
        directional_signs = mover_signs + ([1 if trigger_return >= 0 else -1] if trigger_returns else [])
        dominant_sign = 1 if sum(directional_signs) >= 0 else -1
        alignment_ratio = (
            sum(1 for sign in directional_signs if sign == dominant_sign) / len(directional_signs)
            if directional_signs
            else 0.0
        )
        breadth = len(movers) / peer_count if peer_count else 0.0
        intensity = _average([item[2] for item in movers])

        breadth_component = _scale(breadth, 0.35, 0.85)
        intensity_component = _scale(intensity, 1.6, 4.0)
        alignment_component = _scale(alignment_ratio, 0.6, 1.0)
        synchronicity_component = (
            (breadth_component * 0.45)
            + (intensity_component * 0.35)
            + (alignment_component * 0.20)
        )

        affected_symbols = [symbol for symbol, _, _ in sorted(movers, key=lambda item: item[2], reverse=True)]
        sector_name = context.sector or "sector"
        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_CROSS_ASSET_SYNCHRONOUS_MOVE,
            summary=(
                f"{sector_name} is showing a synchronized cross-asset move with "
                f"{len(movers)}/{peer_count} peers printing simultaneous abnormal returns."
            ),
            component_scores={
                "synchronicity": _clamp01(synchronicity_component),
                "price": _clamp01(_scale(abs(trigger_return), 0.01, 0.05) * 0.4),
            },
            metrics={
                "simultaneous_zscore_count": float(len(movers)),
                "sector_breadth_spike": float(breadth),
                "cluster_movement_intensity": float(intensity),
                "alignment_ratio": float(alignment_ratio),
            },
            confidence=_clamp01((synchronicity_component * 0.80) + (alignment_ratio * 0.20)),
            explainability={
                "what_happened": f"{sector_name} started moving as a coordinated cluster rather than isolated names.",
                "unusualness": "Measured via sector breadth, simultaneous z-score count and alignment.",
                "relative_to": sector_name,
                "relative_to_btc": None,
                "market_wide": True,
            },
            scope=ANOMALY_SCOPE_SECTOR,
            isolated=False,
            related_to=sector_name,
            affected_symbols=affected_symbols,
        )
