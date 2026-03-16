from src.apps.indicators.models import CoinMetrics
from src.apps.patterns.models import MarketCycle
from src.apps.cross_market.models import SectorMetric
from src.apps.market_data.domain import ensure_utc
from src.apps.patterns.cache import read_cached_regime
from src.apps.patterns.domain.regime import read_regime_details


def calculate_priority_score(
    *,
    confidence: float,
    pattern_temperature: float,
    regime_alignment: float,
    volatility_alignment: float,
    liquidity_score: float,
) -> float:
    return max(confidence * pattern_temperature * regime_alignment * volatility_alignment * liquidity_score, 0.0)


def _regime_alignment(regime: str | None, bias: int) -> float:
    if regime in {"bull_trend", "bull_market"}:
        return 1.25 if bias > 0 else 0.75
    if regime in {"bear_trend", "bear_market"}:
        return 1.25 if bias < 0 else 0.75
    if regime in {"sideways_range", "accumulation"}:
        return 1.05 if bias > 0 else 0.95
    if regime in {"distribution", "high_volatility"}:
        return 1.1 if bias < 0 else 0.85
    if regime == "low_volatility":
        return 1.05
    return 1.0


def _volatility_alignment(signal_type: str, metrics: CoinMetrics | None) -> float:
    bb_width = float(metrics.bb_width or 0.0) if metrics is not None else 0.0
    volatility = float(metrics.volatility or 0.0) if metrics is not None else 0.0
    if signal_type.endswith("bollinger_squeeze"):
        return 1.15 if bb_width < 0.05 else 0.9
    if signal_type.endswith("atr_spike") or signal_type.endswith("bollinger_expansion"):
        return 1.15 if volatility > 0 else 1.0
    if volatility > 0 and bb_width > 0.08:
        return 1.08
    return 1.0


def _liquidity_score(metrics: CoinMetrics | None) -> float:
    if metrics is None:
        return 1.0
    volume_change = float(metrics.volume_change_24h or 0.0)
    market_cap = float(metrics.market_cap or 0.0)
    score = 1.0
    if volume_change > 20:
        score += 0.15
    elif volume_change < -20:
        score -= 0.15
    if market_cap > 10_000_000_000:
        score += 0.1
    elif 0 < market_cap < 500_000_000:
        score -= 0.1
    return max(score, 0.4)


def _sector_alignment(sector_metric: SectorMetric | None, bias: int) -> float:
    if sector_metric is None:
        return 1.0
    if sector_metric.sector_strength > 0 and bias > 0:
        return 1.12
    if sector_metric.sector_strength < 0 and bias < 0:
        return 1.12
    if sector_metric.relative_strength < 0 and bias > 0:
        return 0.88
    if sector_metric.relative_strength > 0 and bias < 0:
        return 0.88
    return 1.0


def _cycle_alignment(cycle: MarketCycle | None, bias: int) -> float:
    if cycle is None:
        return 1.0
    if cycle.cycle_phase in {"ACCUMULATION", "EARLY_MARKUP", "MARKUP"}:
        return 1.15 if bias > 0 else 0.82
    if cycle.cycle_phase in {"DISTRIBUTION", "EARLY_MARKDOWN", "MARKDOWN", "CAPITULATION"}:
        return 1.15 if bias < 0 else 0.82
    if cycle.cycle_phase == "LATE_MARKUP":
        return 0.92 if bias > 0 else 1.05
    return 1.0


def _signal_regime(metrics: CoinMetrics | None, timeframe: int) -> str | None:
    if metrics is not None:
        cached = read_cached_regime(coin_id=metrics.coin_id, timeframe=timeframe)
        if cached is not None:
            return cached.regime
    if metrics is None:
        return None
    detailed = read_regime_details(metrics.market_regime_details, timeframe)
    return detailed.regime if detailed is not None else metrics.market_regime


__all__ = [
    "_cycle_alignment",
    "_liquidity_score",
    "_regime_alignment",
    "_sector_alignment",
    "_signal_regime",
    "_volatility_alignment",
    "calculate_priority_score",
]
