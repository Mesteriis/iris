from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from math import sqrt
from typing import TypedDict

from iris.apps.anomalies.constants import ANOMALY_TYPE_CROSS_EXCHANGE_DISLOCATION
from iris.apps.anomalies.schemas import AnomalyDetectionContext, DetectorFinding, MarketStructurePoint


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    size = len(ordered)
    midpoint = size // 2
    if size % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


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


def _price(point: MarketStructurePoint) -> float | None:
    return point.reference_price if point.reference_price not in (None, 0.0) else None


class _SpreadRow(TypedDict):
    timestamp: datetime
    spread_pct: float
    basis_dispersion: float
    venues: list[str]


def _aggregate_spreads(venue_snapshots: dict[str, list[MarketStructurePoint]]) -> list[_SpreadRow]:
    grouped: dict[datetime, list[MarketStructurePoint]] = defaultdict(list)
    for snapshots in venue_snapshots.values():
        for point in snapshots:
            grouped[point.timestamp].append(point)

    rows: list[_SpreadRow] = []
    for timestamp in sorted(grouped):
        points = grouped[timestamp]
        prices = [(point.venue, _price(point)) for point in points]
        valid_prices = [(venue, price) for venue, price in prices if price is not None]
        if len(valid_prices) < 2:
            continue
        values = [price for _, price in valid_prices]
        median_price = _median(values)
        spread_pct = ((max(values) - min(values)) / median_price) if median_price > 0 else 0.0
        basis_values = [point.basis_value for point in points if point.basis_value is not None]
        basis_dispersion = (max(basis_values) - min(basis_values)) if len(basis_values) >= 2 else 0.0
        rows.append(
            {
                "timestamp": timestamp,
                "spread_pct": spread_pct,
                "basis_dispersion": basis_dispersion,
                "venues": [venue for venue, _ in valid_prices],
            }
        )
    return rows


class CrossExchangeDislocationDetector:
    def __init__(self, *, lookback: int = 24) -> None:
        self._lookback = max(lookback, 12)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        spread_rows = _aggregate_spreads(context.venue_snapshots)
        if len(spread_rows) < 8:
            return None

        rows = spread_rows[-self._lookback :]
        current = rows[-1]
        baseline = rows[:-1]
        current_spread = float(current["spread_pct"])
        baseline_spreads = [float(row["spread_pct"]) for row in baseline]
        spread_std = _stddev(baseline_spreads)
        spread_mean = _average(baseline_spreads)
        spread_z = abs(current_spread - spread_mean) / spread_std if spread_std > 0 else current_spread / max(spread_mean, 1e-6)

        current_basis_dispersion = float(current["basis_dispersion"])
        baseline_basis = [float(row["basis_dispersion"]) for row in baseline]
        basis_std = _stddev(baseline_basis)
        basis_mean = _average(baseline_basis)
        basis_z = (
            abs(current_basis_dispersion - basis_mean) / basis_std
            if basis_std > 0
            else current_basis_dispersion / max(basis_mean, 1e-6)
        )
        dislocation_duration = 1
        for row in reversed(baseline):
            if float(row["spread_pct"]) >= max(spread_mean * 1.5, 0.004):
                dislocation_duration += 1
            else:
                break

        liquidity_component = _scale(spread_z, 1.2, 4.5)
        relative_component = _scale(current_spread, 0.003, 0.03)
        basis_component = _scale(basis_z, 1.0, 4.0)
        persistence_component = _scale(float(dislocation_duration), 1.0, 5.0)
        dislocation_component = (
            (liquidity_component * 0.42)
            + (relative_component * 0.28)
            + (basis_component * 0.15)
            + (persistence_component * 0.15)
        )
        if current_spread < 0.004 or dislocation_component < 0.45:
            return None

        venues = list(current["venues"])
        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_CROSS_EXCHANGE_DISLOCATION,
            summary=(
                f"{context.symbol} is trading on a meaningful cross-exchange dislocation across "
                f"{len(venues)} venues."
            ),
            component_scores={
                "liquidity": _clamp01(dislocation_component),
                "relative": _clamp01((basis_component * 0.55) + (relative_component * 0.45)),
            },
            metrics={
                "venue_spread_zscore": float(spread_z),
                "venue_spread_pct": float(current_spread),
                "basis_dispersion_zscore": float(basis_z),
                "dislocation_duration": float(dislocation_duration),
            },
            confidence=_clamp01((dislocation_component * 0.72) + (persistence_component * 0.28)),
            explainability={
                "what_happened": f"{context.symbol} stopped pricing uniformly across venues.",
                "unusualness": "Measured via venue spread z-score, basis dispersion and persistence.",
                "relative_to": "cross-exchange venue pricing",
                "relative_to_btc": None,
                "market_wide": False,
            },
            isolated=len(venues) <= 3,
            affected_symbols=venues,
        )
