from dataclasses import dataclass
from collections.abc import Sequence

from src.apps.cross_market.models import SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.patterns.domain.narrative import SectorNarrative
from src.apps.patterns.domain.semantics import is_cluster_signal, is_hierarchy_signal, is_pattern_signal
from src.apps.patterns.models import MarketCycle
from src.apps.signals.models import Signal

DECISION_TYPES = [
    "STRONG_BUY",
    "BUY",
    "ACCUMULATE",
    "HOLD",
    "REDUCE",
    "SELL",
    "STRONG_SELL",
]
RECENT_DECISION_LOOKBACK_DAYS = 30
MATERIAL_SCORE_DELTA = 0.03
MATERIAL_CONFIDENCE_DELTA = 0.03


@dataclass(slots=True, frozen=True)
class DecisionFactors:
    signal_priority: float
    regime_alignment: float
    sector_strength: float
    cycle_alignment: float
    historical_pattern_success: float
    strategy_alignment: float


def calculate_decision_score(
    *,
    signal_priority: float,
    regime_alignment: float,
    sector_strength: float,
    cycle_alignment: float,
    historical_pattern_success: float,
    strategy_alignment: float = 1.0,
) -> float:
    return max(
        signal_priority
        * regime_alignment
        * sector_strength
        * cycle_alignment
        * historical_pattern_success,
        0.0,
    ) * max(strategy_alignment, 0.0)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _regime_alignment(signals: Sequence[Signal]) -> float:
    if not signals:
        return 1.0
    return sum(float(signal.regime_alignment or 1.0) for signal in signals) / len(signals)


def _cycle_alignment(cycle: MarketCycle | None, bias: int) -> float:
    if cycle is None:
        return 1.0
    if cycle.cycle_phase in {"ACCUMULATION", "EARLY_MARKUP", "MARKUP"}:
        return 1.18 if bias > 0 else 0.82
    if cycle.cycle_phase == "LATE_MARKUP":
        return 0.95 if bias > 0 else 1.06
    if cycle.cycle_phase in {"DISTRIBUTION", "EARLY_MARKDOWN", "MARKDOWN", "CAPITULATION"}:
        return 1.18 if bias < 0 else 0.82
    return 1.0


def _sector_strength_factor(
    coin: Coin,
    metrics: CoinMetrics | None,
    sector_metric: SectorMetric | None,
    narrative: SectorNarrative | None,
) -> float:
    if sector_metric is None:
        return 1.0
    factor = 1.0
    factor += _clamp(float(sector_metric.sector_strength) * 3.0, -0.2, 0.2)
    factor += _clamp(float(sector_metric.relative_strength) * 3.0, -0.15, 0.15)
    if narrative is not None and coin.sector is not None and narrative.top_sector == coin.sector.name:
        factor += 0.05
    market_cap = float(metrics.market_cap or 0.0) if metrics is not None else 0.0
    if narrative is not None:
        if narrative.capital_wave == "btc" and coin.symbol != "BTCUSD":
            factor -= 0.05
        elif narrative.capital_wave == "large_caps" and market_cap >= 10_000_000_000:
            factor += 0.05
        elif (
            narrative.capital_wave == "sector_leaders"
            and coin.sector is not None
            and narrative.top_sector == coin.sector.name
        ):
            factor += 0.05
        elif narrative.capital_wave == "mid_caps" and 1_000_000_000 <= market_cap < 10_000_000_000:
            factor += 0.04
        elif narrative.capital_wave == "micro_caps" and 0 < market_cap < 500_000_000:
            factor += 0.05
    return _clamp(factor, 0.65, 1.35)


def _decision_from_score(score: float, bias_ratio: float) -> str:
    if abs(bias_ratio) < 0.18 or score < 0.45:
        return "HOLD"
    if bias_ratio > 0:
        if score >= 1.65 and abs(bias_ratio) >= 0.55:
            return "STRONG_BUY"
        if score >= 1.1:
            return "BUY"
        return "ACCUMULATE"
    if score >= 1.65 and abs(bias_ratio) >= 0.55:
        return "STRONG_SELL"
    if score >= 1.1:
        return "SELL"
    return "REDUCE"


def _decision_confidence(score: float, bias_ratio: float, factors: DecisionFactors) -> float:
    base = _clamp(score / 2.5, 0.0, 0.98)
    directionality = 0.55 + min(abs(bias_ratio), 1.0) * 0.45
    stability = _clamp(
        (
            factors.regime_alignment
            + factors.cycle_alignment
            + factors.historical_pattern_success
            + factors.sector_strength
            + factors.strategy_alignment
        )
        / 5,
        0.5,
        1.2,
    )
    return _clamp(base * directionality * stability, 0.05, 0.99)


def _decision_reason(
    *,
    decision: str,
    score: float,
    bias_ratio: float,
    signals: Sequence[Signal],
    regime: str | None,
    sector_metric: SectorMetric | None,
    narrative: SectorNarrative | None,
    cycle: MarketCycle | None,
    historical_pattern_success: float,
    strategy_alignment_value: float,
    matched_strategies: Sequence[str],
) -> str:
    cluster_count = sum(1 for signal in signals if is_cluster_signal(str(signal.signal_type)))
    hierarchy_count = sum(1 for signal in signals if is_hierarchy_signal(str(signal.signal_type)))
    base_patterns = sum(1 for signal in signals if is_pattern_signal(str(signal.signal_type)))
    bias_label = "bullish" if bias_ratio > 0.18 else "bearish" if bias_ratio < -0.18 else "neutral"
    sector_strength = float(sector_metric.sector_strength) if sector_metric is not None else 0.0
    capital_wave = narrative.capital_wave if narrative is not None else None
    top_sector = narrative.top_sector if narrative is not None else None
    strategy_names = ", ".join(name[:48] for name in matched_strategies[:2]) if matched_strategies else "none"
    return (
        f"{decision}: {bias_label} stack {base_patterns} patterns/{cluster_count} clusters/{hierarchy_count} hierarchies; "
        f"regime={regime or 'unknown'}; "
        f"cycle={cycle.cycle_phase if cycle is not None else 'unknown'}; "
        f"sector_strength={sector_strength:.4f}; "
        f"top_sector={top_sector or 'n/a'}; "
        f"capital_wave={capital_wave or 'n/a'}; "
        f"historical_success={historical_pattern_success:.2f}; "
        f"strategy_alignment={strategy_alignment_value:.2f}; "
        f"strategies={strategy_names}; "
        f"score={score:.3f}"
    )


__all__ = [
    "DECISION_TYPES",
    "DecisionFactors",
    "MATERIAL_CONFIDENCE_DELTA",
    "MATERIAL_SCORE_DELTA",
    "RECENT_DECISION_LOOKBACK_DAYS",
    "_clamp",
    "_cycle_alignment",
    "_decision_confidence",
    "_decision_from_score",
    "_decision_reason",
    "_regime_alignment",
    "_sector_strength_factor",
    "calculate_decision_score",
]
