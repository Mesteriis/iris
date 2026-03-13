from __future__ import annotations

from collections.abc import Sequence

from src.apps.anomalies.constants import ANOMALY_TYPE_CORRELATION_BREAKDOWN
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


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    left_std = _stddev(left)
    right_std = _stddev(right)
    if left_std <= 0 or right_std <= 0:
        return 0.0
    return _covariance(left, right) / (left_std * right_std)


def _beta(left: Sequence[float], right: Sequence[float]) -> float:
    variance = _stddev(right) ** 2
    if variance <= 0:
        return 1.0
    return _covariance(left, right) / variance


def _scale(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return _clamp01((value - floor) / (ceiling - floor))


def _returns(candles: Sequence[CandlePoint]) -> list[float]:
    values: list[float] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        previous_close = float(previous.close)
        values.append((float(current.close) - previous_close) / previous_close if previous_close else 0.0)
    return values


def _aligned_returns(*series: list[float]) -> list[list[float]]:
    size = min((len(item) for item in series), default=0)
    if size <= 0:
        return [[] for _ in series]
    return [item[-size:] for item in series]


class CorrelationBreakdownDetector:
    def __init__(self, *, lookback: int = 48, short_window: int = 6) -> None:
        self._lookback = max(lookback, 32)
        self._short_window = max(short_window, 5)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        if context.benchmark is None:
            return None

        coin_returns, benchmark_returns = _aligned_returns(
            _returns(context.candles[-(self._lookback + 2) :]),
            _returns(context.benchmark.candles[-(self._lookback + 2) :]),
        )
        if len(coin_returns) < self._short_window + 18 or len(benchmark_returns) < self._short_window + 18:
            return None

        baseline_coin = coin_returns[:-self._short_window][-24:]
        baseline_benchmark = benchmark_returns[:-self._short_window][-24:]
        recent_coin = coin_returns[-self._short_window :]
        recent_benchmark = benchmark_returns[-self._short_window :]
        if len(baseline_coin) < 12 or len(recent_coin) < self._short_window:
            return None

        long_corr = _correlation(baseline_coin, baseline_benchmark)
        short_corr = _correlation(recent_coin, recent_benchmark)
        if abs(long_corr) < 0.45:
            return None

        corr_drop = abs(long_corr - short_corr)
        long_beta = _beta(baseline_coin, baseline_benchmark)
        short_beta = _beta(recent_coin, recent_benchmark)
        beta_shift = abs(long_beta - short_beta)

        long_residuals = [
            coin_return - (long_beta * benchmark_return)
            for coin_return, benchmark_return in zip(baseline_coin, baseline_benchmark, strict=False)
        ]
        recent_residuals = [
            coin_return - (long_beta * benchmark_return)
            for coin_return, benchmark_return in zip(recent_coin, recent_benchmark, strict=False)
        ]
        baseline_residual_std = _stddev(long_residuals)
        recent_residual_std = _stddev(recent_residuals)
        residual_floor = max(
            baseline_residual_std,
            _stddev(baseline_coin) * 0.10,
            _stddev(baseline_benchmark) * 0.10,
            1e-6,
        )
        residual_variance_ratio = (
            recent_residual_std / residual_floor
        )

        peer_latest_returns: list[float] = []
        for peer_candles in list(context.sector_peer_candles.values()) + list(context.related_peer_candles.values()):
            peer_history = _returns(peer_candles[-(self._lookback + 2) :])
            if peer_history:
                peer_latest_returns.append(peer_history[-1])
        current_coin_return = recent_coin[-1]
        peer_dispersion = abs(current_coin_return - _average(peer_latest_returns)) if peer_latest_returns else 0.0

        corr_component = _scale(corr_drop, 0.20, 1.10)
        beta_component = _scale(beta_shift, 0.20, 1.40)
        residual_component = _scale(residual_variance_ratio, 1.15, 4.0)
        peer_component = _scale(peer_dispersion, 0.01, 0.07)
        relative_component = (
            (corr_component * 0.45)
            + (beta_component * 0.20)
            + (residual_component * 0.25)
            + (peer_component * 0.10)
        )
        if corr_drop < 0.30 or residual_variance_ratio < 1.2 or relative_component < 0.44:
            return None

        confirmation_hits = sum(
            1
            for residual in recent_residuals[-3:]
            if abs(residual) >= max(residual_floor * 1.10, 1e-9)
        )
        relative_to = context.benchmark.symbol
        if context.sector_peer_candles:
            relative_to = f"{relative_to} and {context.sector or 'sector'} peers"

        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_CORRELATION_BREAKDOWN,
            summary=f"{context.symbol} has started decoupling from its usual benchmark/correlation structure.",
            component_scores={
                "relative": _clamp01(relative_component),
                "volatility": _clamp01((residual_component * 0.65) + (corr_component * 0.35)),
            },
            metrics={
                "long_correlation": float(long_corr),
                "short_correlation": float(short_corr),
                "correlation_drop": float(corr_drop),
                "beta_shift": float(beta_shift),
                "residual_variance_ratio": float(residual_variance_ratio),
                "peer_dispersion": float(peer_dispersion),
            },
            confidence=_clamp01((relative_component * 0.72) + (_scale(abs(long_corr), 0.45, 1.0) * 0.28)),
            explainability={
                "what_happened": f"{context.symbol} stopped tracking its usual benchmark behavior.",
                "unusualness": "Measured via correlation drop, beta instability and residual variance expansion.",
                "relative_to": relative_to,
                "relative_to_btc": "decoupling",
                "market_wide": False,
            },
            requires_confirmation=True,
            confirmation_hits=confirmation_hits,
            confirmation_target=2,
            isolated=(not peer_latest_returns) or peer_dispersion >= abs(recent_benchmark[-1]),
            related_to=relative_to,
        )
