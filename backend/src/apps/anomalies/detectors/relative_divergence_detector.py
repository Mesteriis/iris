from collections.abc import Sequence

from src.apps.anomalies.constants import ANOMALY_TYPE_RELATIVE_DIVERGENCE
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


def _covariance(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = _average(left)
    right_mean = _average(right)
    return sum((lval - left_mean) * (rval - right_mean) for lval, rval in zip(left, right, strict=False)) / len(left)


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


def _aligned_returns(*series: list[float]) -> list[list[float]]:
    size = min((len(item) for item in series), default=0)
    if size <= 0:
        return [[] for _ in series]
    return [item[-size:] for item in series]


class RelativeDivergenceDetector:
    def __init__(self, *, lookback: int = 48) -> None:
        self._lookback = max(lookback, 24)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        if context.benchmark is None:
            return None

        coin_returns, benchmark_returns = _aligned_returns(
            _returns(context.candles[-(self._lookback + 2) :]),
            _returns(context.benchmark.candles[-(self._lookback + 2) :]),
        )
        if len(coin_returns) < 12 or len(benchmark_returns) < 12:
            return None

        baseline_coin = coin_returns[:-1]
        baseline_benchmark = benchmark_returns[:-1]
        benchmark_variance = _stddev(baseline_benchmark) ** 2
        beta = _covariance(baseline_coin, baseline_benchmark) / benchmark_variance if benchmark_variance > 0 else 1.0
        residuals = [
            coin_return - (beta * benchmark_return)
            for coin_return, benchmark_return in zip(coin_returns, benchmark_returns, strict=False)
        ]
        baseline_residuals = residuals[:-1]
        current_residual = residuals[-1]
        residual_std = _stddev(baseline_residuals)
        residual_mean = _average(baseline_residuals)
        residual_z = abs(current_residual - residual_mean) / residual_std if residual_std > 0 else 0.0

        current_coin_return = coin_returns[-1]
        current_benchmark_return = benchmark_returns[-1]
        sector_gap = 0.0
        related_gap = 0.0
        peer_returns: list[float] = []

        for peer_candles in list(context.sector_peer_candles.values()) + list(context.related_peer_candles.values()):
            peer_history = _returns(peer_candles[-(self._lookback + 2) :])
            if not peer_history:
                continue
            peer_returns.append(peer_history[-1])
        if peer_returns:
            peer_average = _average(peer_returns)
            sector_gap = current_coin_return - peer_average
            related_gap = current_residual - (peer_average - current_benchmark_return)

        residual_component = _scale(residual_z, 1.1, 4.0)
        sector_component = _scale(abs(sector_gap), 0.01, 0.06)
        related_component = _scale(abs(related_gap), 0.01, 0.08)
        relative_component = (
            (residual_component * 0.55)
            + (sector_component * 0.25)
            + (related_component * 0.20)
        )
        confirmation_hits = sum(
            1
            for residual in residuals[-2:]
            if abs(residual) >= max(residual_std * 1.05, 1e-9) and (residual == 0 or residual * current_residual > 0)
        )

        relationship = "outperform" if current_residual >= 0 else "underperform"
        isolated = abs(sector_gap) >= abs(current_benchmark_return)
        relative_to = context.benchmark.symbol
        if context.sector_peer_candles:
            relative_to = f"{relative_to} and {context.sector or 'sector'} peers"

        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_RELATIVE_DIVERGENCE,
            summary=f"{context.symbol} is {relationship}ing {relative_to} on a beta-adjusted basis.",
            component_scores={
                "relative": _clamp01(relative_component),
                "price": _clamp01(residual_component * 0.35),
            },
            metrics={
                "beta_adjusted_deviation": float(current_residual),
                "residual_return_zscore": float(residual_z),
                "sector_gap": float(sector_gap),
                "benchmark_return": float(current_benchmark_return),
            },
            confidence=_clamp01((relative_component * 0.75) + (confirmation_hits / 2.0 * 0.25)),
            explainability={
                "what_happened": f"{context.symbol} decoupled from its benchmark behavior.",
                "unusualness": "Measured as a beta-adjusted residual return versus the benchmark and peers.",
                "relative_to": relative_to,
                "relative_to_btc": relationship,
                "market_wide": not isolated,
            },
            requires_confirmation=True,
            confirmation_hits=confirmation_hits,
            confirmation_target=2,
            isolated=isolated,
            related_to=relative_to,
        )
