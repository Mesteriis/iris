from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from iris.apps.indicators.models import CoinMetrics
from iris.apps.patterns.domain.regime import read_regime_details
from iris.apps.patterns.domain.semantics import pattern_bias, slug_from_signal_type

FUSION_SIGNAL_LIMIT = 20
FUSION_CANDLE_GROUPS = 3
WATCH_MIN_TOTAL_SCORE = 0.55
MATERIAL_CONFIDENCE_DELTA = 0.03
NEWS_FUSION_MAX_ITEMS = 12
NEWS_FUSION_SCORE_CAP = 0.85
FUSION_NEWS_TIMEFRAMES = (15, 60, 240, 1440)

CONTINUATION_SLUGS = {
    "bull_flag",
    "bear_flag",
    "pennant",
    "breakout_retest",
    "consolidation_breakout",
    "high_tight_flag",
    "measured_move_bullish",
    "measured_move_bearish",
    "pullback_continuation_bullish",
    "pullback_continuation_bearish",
    "trend_continuation",
    "cluster_bullish",
    "cluster_bearish",
}
REVERSAL_SLUGS = {
    "head_shoulders",
    "inverse_head_shoulders",
    "double_top",
    "double_bottom",
    "triple_top",
    "triple_bottom",
    "rising_wedge",
    "falling_wedge",
    "momentum_exhaustion",
    "trend_exhaustion",
    "accumulation",
    "distribution",
}
BREAKOUT_SLUGS = {
    "ascending_triangle",
    "descending_triangle",
    "symmetrical_triangle",
    "bollinger_squeeze",
    "bollinger_expansion",
    "atr_spike",
    "volatility_expansion_breakout",
    "squeeze_breakout",
    "narrow_range_breakout",
}
MEAN_REVERSION_SLUGS = {
    "rsi_divergence",
    "macd_divergence",
    "volume_divergence",
    "mean_reversion_snap",
}


@dataclass(slots=True, frozen=True)
class FusionSnapshot:
    decision: str
    confidence: float
    signal_count: int
    regime: str | None
    bullish_score: float
    bearish_score: float
    agreement: float
    latest_timestamp: datetime
    news_item_count: int = 0
    news_bullish_score: float = 0.0
    news_bearish_score: float = 0.0


@dataclass(slots=True, frozen=True)
class NewsImpactSnapshot:
    item_count: int
    bullish_score: float
    bearish_score: float
    latest_timestamp: datetime


class _WeightedSignal(Protocol):
    @property
    def signal_type(self) -> str: ...

    @property
    def confidence(self) -> float: ...


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _signal_regime(metrics: CoinMetrics | None, timeframe: int) -> str | None:
    if metrics is None:
        return None
    snapshot = read_regime_details(metrics.market_regime_details, timeframe)
    return snapshot.regime if snapshot is not None else metrics.market_regime


def _signal_archetype(signal_type: str) -> str:
    slug = slug_from_signal_type(signal_type) or signal_type.removeprefix("pattern_")
    if slug in CONTINUATION_SLUGS:
        return "continuation"
    if slug in REVERSAL_SLUGS:
        return "reversal"
    if slug in BREAKOUT_SLUGS:
        return "breakout"
    if slug in MEAN_REVERSION_SLUGS:
        return "mean_reversion"
    return "generic"


def _regime_weight(signal: _WeightedSignal, regime: str | None) -> float:
    slug = slug_from_signal_type(signal.signal_type) or signal.signal_type
    bias = pattern_bias(slug, fallback_price_delta=signal.confidence - 0.5)
    archetype = _signal_archetype(signal.signal_type)
    if regime == "bull_trend":
        if archetype == "continuation":
            return 1.2 if bias > 0 else 0.8
        if archetype == "reversal":
            return 0.85 if bias < 0 else 1.05
    if regime == "bear_trend":
        if archetype == "continuation":
            return 1.2 if bias < 0 else 0.8
        if archetype == "reversal":
            return 0.85 if bias > 0 else 1.05
    if regime == "sideways_range":
        if archetype == "mean_reversion":
            return 1.2
        if archetype in {"continuation", "breakout"}:
            return 0.85
    if regime == "high_volatility":
        if archetype == "breakout":
            return 1.2
        if archetype == "mean_reversion":
            return 0.9
    if regime == "low_volatility":
        if archetype == "breakout":
            return 0.9
        if archetype == "continuation":
            return 1.05
    return 1.0


def _decision_from_scores(*, bullish_score: float, bearish_score: float, total_score: float) -> tuple[str, float]:
    directional_score = bullish_score + bearish_score
    if directional_score <= 0 and total_score < WATCH_MIN_TOTAL_SCORE:
        return "WATCH", 0.2
    dominance = abs(bullish_score - bearish_score) / directional_score
    if bullish_score > 0 and bearish_score > 0 and dominance < 0.2:
        return "HOLD", _clamp(0.4 + (1.0 - dominance) * 0.3 + min(total_score / 4, 0.15), 0.35, 0.86)
    if total_score < WATCH_MIN_TOTAL_SCORE:
        return "WATCH", 0.22
    if bullish_score > bearish_score:
        return "BUY", _clamp(0.45 + dominance * 0.35 + min(total_score / 4, 0.22), 0.3, 0.96)
    return "SELL", _clamp(0.45 + dominance * 0.35 + min(total_score / 4, 0.22), 0.3, 0.96)


def _apply_news_impact(
    fused: FusionSnapshot,
    news_impact: NewsImpactSnapshot | None,
) -> FusionSnapshot:
    if news_impact is None or news_impact.item_count <= 0:
        return fused
    bullish_score = fused.bullish_score + news_impact.bullish_score
    bearish_score = fused.bearish_score + news_impact.bearish_score
    total_score = bullish_score + bearish_score
    decision, confidence = _decision_from_scores(
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        total_score=total_score,
    )
    agreement = abs(bullish_score - bearish_score) / max(total_score, 1e-9)
    return FusionSnapshot(
        decision=decision,
        confidence=confidence,
        signal_count=fused.signal_count,
        regime=fused.regime,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        agreement=_clamp(agreement, 0.0, 1.0),
        latest_timestamp=max(fused.latest_timestamp, news_impact.latest_timestamp),
        news_item_count=news_impact.item_count,
        news_bullish_score=news_impact.bullish_score,
        news_bearish_score=news_impact.bearish_score,
    )


__all__ = [
    "FUSION_CANDLE_GROUPS",
    "FUSION_NEWS_TIMEFRAMES",
    "FUSION_SIGNAL_LIMIT",
    "MATERIAL_CONFIDENCE_DELTA",
    "NEWS_FUSION_MAX_ITEMS",
    "NEWS_FUSION_SCORE_CAP",
    "FusionSnapshot",
    "NewsImpactSnapshot",
    "_apply_news_impact",
    "_clamp",
    "_decision_from_scores",
    "_regime_weight",
    "_signal_archetype",
    "_signal_regime",
]
