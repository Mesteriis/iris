from collections import defaultdict
from collections.abc import Sequence

from src.apps.anomalies.constants import ANOMALY_TYPE_FUNDING_OPEN_INTEREST_ANOMALY
from src.apps.anomalies.schemas import AnomalyDetectionContext, DetectorFinding, MarketStructurePoint


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


def _aggregate_series(venue_snapshots: dict[str, list[MarketStructurePoint]]) -> list[dict[str, float]]:
    grouped: dict[object, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for snapshots in venue_snapshots.values():
        for point in snapshots:
            if point.funding_rate is not None:
                grouped[point.timestamp]["funding"].append(float(point.funding_rate))
            if point.open_interest is not None:
                grouped[point.timestamp]["open_interest"].append(float(point.open_interest))
            basis_value = point.basis_value
            if basis_value is not None:
                grouped[point.timestamp]["basis"].append(float(basis_value))
    rows: list[dict[str, float]] = []
    for timestamp in sorted(grouped):
        item = grouped[timestamp]
        if not item:
            continue
        rows.append(
            {
                "funding": _average(item.get("funding", [])),
                "open_interest": sum(item.get("open_interest", [])),
                "basis": _average(item.get("basis", [])),
            }
        )
    return rows


class FundingOpenInterestDetector:
    def __init__(self, *, lookback: int = 24) -> None:
        self._lookback = max(lookback, 12)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        aggregated = _aggregate_series(context.venue_snapshots)
        if len(aggregated) < 12 or len(context.candles) < 2:
            return None

        series = aggregated[-self._lookback :]
        funding_values = [row["funding"] for row in series if row["funding"] != 0.0]
        open_interest_values = [row["open_interest"] for row in series if row["open_interest"] > 0.0]
        basis_values = [row["basis"] for row in series]
        if len(funding_values) < 8 or len(open_interest_values) < 8:
            return None

        current_funding = funding_values[-1]
        current_oi = open_interest_values[-1]
        current_basis = basis_values[-1]
        funding_baseline = funding_values[:-1]
        oi_baseline = open_interest_values[:-1]
        basis_baseline = basis_values[:-1]

        funding_std = _stddev(funding_baseline)
        funding_mean = _average(funding_baseline)
        funding_z = abs(current_funding - funding_mean) / funding_std if funding_std > 0 else abs(current_funding) * 10000.0
        oi_average = _average(oi_baseline[-12:])
        oi_ratio = current_oi / oi_average if oi_average > 0 else 0.0
        basis_std = _stddev(basis_baseline)
        basis_mean = _average(basis_baseline)
        basis_z = abs(current_basis - basis_mean) / basis_std if basis_std > 0 else abs(current_basis) * 100.0

        latest_close = float(context.candles[-1].close)
        previous_close = float(context.candles[-2].close)
        current_return = ((latest_close - previous_close) / previous_close) if previous_close else 0.0
        oi_adjusted_move = abs(current_return) * max(oi_ratio, 1.0)

        funding_component = _scale(funding_z, 1.5, 5.5)
        oi_component = _scale(oi_ratio, 1.15, 2.8)
        basis_component = _scale(basis_z, 1.0, 4.0)
        move_component = _scale(oi_adjusted_move, 0.01, 0.08)
        derivatives_component = (
            (funding_component * 0.32)
            + (oi_component * 0.33)
            + (basis_component * 0.20)
            + (move_component * 0.15)
        )
        if max(funding_component, oi_component, basis_component) < 0.35 or derivatives_component < 0.45:
            return None

        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_FUNDING_OPEN_INTEREST_ANOMALY,
            summary=(
                f"{context.symbol} is showing an abnormal derivatives positioning shift via funding, "
                "open interest and basis expansion."
            ),
            component_scores={
                "derivatives": _clamp01(derivatives_component),
                "price": _clamp01(move_component * 0.55),
                "relative": _clamp01(basis_component * 0.65),
            },
            metrics={
                "funding_zscore": float(funding_z),
                "open_interest_ratio": float(oi_ratio),
                "basis_zscore": float(basis_z),
                "oi_adjusted_move": float(oi_adjusted_move),
            },
            confidence=_clamp01((derivatives_component * 0.74) + (max(funding_component, oi_component) * 0.26)),
            explainability={
                "what_happened": f"{context.symbol} showed an abnormal shift in leveraged positioning.",
                "unusualness": "Measured via funding spike, open-interest expansion and basis divergence.",
                "relative_to": "its own rolling derivatives baseline",
                "relative_to_btc": None,
                "market_wide": False,
            },
        )
