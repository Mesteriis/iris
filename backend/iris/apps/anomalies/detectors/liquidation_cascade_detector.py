from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from math import sqrt

from iris.apps.anomalies.constants import ANOMALY_TYPE_LIQUIDATION_CASCADE
from iris.apps.anomalies.schemas import AnomalyDetectionContext, DetectorFinding, MarketStructurePoint


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


def _aggregate_liquidation_series(venue_snapshots: dict[str, list[MarketStructurePoint]]) -> list[dict[str, float]]:
    grouped: dict[datetime, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for snapshots in venue_snapshots.values():
        for point in snapshots:
            grouped[point.timestamp]["longs"].append(float(point.liquidations_long or 0.0))
            grouped[point.timestamp]["shorts"].append(float(point.liquidations_short or 0.0))
            if point.open_interest is not None:
                grouped[point.timestamp]["open_interest"].append(float(point.open_interest))
    rows: list[dict[str, float]] = []
    for timestamp in sorted(grouped):
        item = grouped[timestamp]
        long_total = sum(item.get("longs", []))
        short_total = sum(item.get("shorts", []))
        rows.append(
            {
                "longs": long_total,
                "shorts": short_total,
                "total": long_total + short_total,
                "open_interest": sum(item.get("open_interest", [])),
            }
        )
    return rows


class LiquidationCascadeDetector:
    def __init__(self, *, lookback: int = 24) -> None:
        self._lookback = max(lookback, 12)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        aggregated = _aggregate_liquidation_series(context.venue_snapshots)
        if len(aggregated) < 8 or len(context.candles) < 3:
            return None

        series = aggregated[-self._lookback :]
        totals = [row["total"] for row in series]
        current_total = totals[-1]
        baseline_totals = totals[:-1]
        if current_total <= 0.0 or len(baseline_totals) < 4:
            return None

        liquidation_std = _stddev(baseline_totals)
        liquidation_mean = _average(baseline_totals)
        liquidation_z = (
            abs(current_total - liquidation_mean) / liquidation_std
            if liquidation_std > 0
            else current_total / max(liquidation_mean, 1.0)
        )
        current = series[-1]
        previous = series[-2]
        oi_drop_ratio = (
            max(previous["open_interest"] - current["open_interest"], 0.0) / previous["open_interest"]
            if previous["open_interest"] > 0
            else 0.0
        )

        latest_close = float(context.candles[-1].close)
        previous_close = float(context.candles[-2].close)
        current_return = ((latest_close - previous_close) / previous_close) if previous_close else 0.0
        historical_returns = []
        for earlier, later in zip(context.candles[:-1], context.candles[1:-1], strict=False):
            earlier_close = float(earlier.close)
            historical_returns.append((float(later.close) - earlier_close) / earlier_close if earlier_close else 0.0)
        return_std = _stddev(historical_returns)
        price_impulse = abs(current_return) / return_std if return_std > 0 else abs(current_return) * 100.0

        directional_liquidations = current["longs"] if current_return < 0 else current["shorts"]
        imbalance = directional_liquidations / current_total if current_total > 0 else 0.0
        liquidity_component = _scale(liquidation_z, 1.5, 6.0)
        derivatives_component = _scale(oi_drop_ratio, 0.01, 0.12)
        volatility_component = _scale(price_impulse, 1.4, 5.5)
        alignment_component = _scale(imbalance, 0.55, 1.0)
        cascade_component = (
            (liquidity_component * 0.35)
            + (derivatives_component * 0.20)
            + (volatility_component * 0.25)
            + (alignment_component * 0.20)
        )
        if liquidation_z < 1.6 or price_impulse < 1.5 or cascade_component < 0.48:
            return None

        cascade_side = "long_flush" if current_return < 0 else "short_squeeze"
        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_LIQUIDATION_CASCADE,
            summary=f"{context.symbol} is showing a liquidation-driven {cascade_side} with forced unwinds across venues.",
            component_scores={
                "liquidity": _clamp01(cascade_component),
                "derivatives": _clamp01((derivatives_component * 0.60) + (alignment_component * 0.40)),
                "volatility": _clamp01(volatility_component),
            },
            metrics={
                "liquidation_zscore": float(liquidation_z),
                "liquidation_total": float(current_total),
                "open_interest_drop_ratio": float(oi_drop_ratio),
                "price_impulse_ratio": float(price_impulse),
                "cascade_alignment": float(imbalance),
            },
            confidence=_clamp01((cascade_component * 0.76) + (alignment_component * 0.24)),
            explainability={
                "what_happened": f"{context.symbol} printed a forced-unwind move consistent with a liquidation cascade.",
                "unusualness": "Measured via liquidation spike, open-interest drop and price impulse alignment.",
                "relative_to": "its own rolling liquidation and derivatives baseline",
                "relative_to_btc": None,
                "market_wide": False,
            },
            requires_confirmation=True,
            confirmation_hits=2 if liquidation_z >= 2.0 else 1,
            confirmation_target=2,
        )
