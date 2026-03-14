from __future__ import annotations

from src.apps.market_data.domain import ensure_utc
from src.apps.patterns.domain.semantics import (
    is_cluster_signal,
    is_hierarchy_signal,
    pattern_bias,
    slug_from_signal_type,
)
from src.apps.signals.engines.contracts import (
    SignalFusionEngineResult,
    SignalFusionExplainability,
    SignalFusionFeatureScore,
    SignalFusionInput,
    SignalFusionSignalInput,
)
from src.apps.signals.fusion_support import (
    WATCH_MIN_TOTAL_SCORE,
    FusionSnapshot,
    NewsImpactSnapshot,
    _apply_news_impact,
    _clamp,
    _decision_from_scores,
    _regime_weight,
)


def resolve_signal_success_rate(
    *,
    signal: SignalFusionSignalInput,
    slug: str | None,
    regime: str | None,
    success_rates: dict[tuple[str, str], float],
) -> float:
    if slug is None:
        if is_cluster_signal(signal.signal_type) or is_hierarchy_signal(signal.signal_type):
            return 0.58
        return 0.55
    if regime is not None and (slug, regime) in success_rates:
        return _clamp(float(success_rates[(slug, regime)]), 0.35, 0.95)
    if (slug, "all") in success_rates:
        return _clamp(float(success_rates[(slug, "all")]), 0.35, 0.95)
    return 0.55


def run_signal_fusion(fusion_input: SignalFusionInput) -> SignalFusionEngineResult | None:
    if not fusion_input.signals:
        return None

    success_rates = {
        (item.pattern_slug, item.market_regime): float(item.success_rate) for item in fusion_input.success_rates
    }
    grouped_timestamps = sorted({ensure_utc(signal.candle_timestamp) for signal in fusion_input.signals}, reverse=True)
    age_by_timestamp = {timestamp: index for index, timestamp in enumerate(grouped_timestamps)}

    bullish_score = 0.0
    bearish_score = 0.0
    feature_scores: dict[str, float] = {}
    for signal in fusion_input.signals:
        age_index = age_by_timestamp[ensure_utc(signal.candle_timestamp)]
        slug = slug_from_signal_type(signal.signal_type)
        success_rate = resolve_signal_success_rate(
            signal=signal,
            slug=slug,
            regime=fusion_input.regime,
            success_rates=success_rates,
        )
        context_factor = _clamp(float(signal.context_score or 1.0), 0.6, 1.4)
        alignment = _clamp(float(signal.regime_alignment or 1.0), 0.6, 1.4)
        priority_factor = _clamp(max(float(signal.priority_score or 0.0), float(signal.confidence)), 0.45, 1.6)
        bias = pattern_bias(slug or signal.signal_type, fallback_price_delta=float(signal.confidence) - 0.5)
        cross_market_factor = fusion_input.bullish_alignment if bias > 0 else fusion_input.bearish_alignment
        recency_weight = max(1.0 - (age_index * 0.1), 0.75)
        score = (
            _clamp(float(signal.confidence), 0.01, 1.0)
            * success_rate
            * _regime_weight(signal, fusion_input.regime)
            * context_factor
            * alignment
            * cross_market_factor
            * priority_factor
            * recency_weight
        )
        label = slug or signal.signal_type
        feature_scores[label] = feature_scores.get(label, 0.0) + (score if bias > 0 else -score)
        if bias > 0:
            bullish_score += score
        else:
            bearish_score += score

    total_score = bullish_score + bearish_score
    decision, confidence = _decision_from_scores(
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        total_score=total_score,
    )
    agreement = abs(bullish_score - bearish_score) / max(bullish_score + bearish_score, 1e-9)
    base_snapshot = FusionSnapshot(
        decision=decision,
        confidence=confidence,
        signal_count=len(fusion_input.signals),
        regime=fusion_input.regime,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        agreement=_clamp(agreement, 0.0, 1.0),
        latest_timestamp=max(ensure_utc(signal.candle_timestamp) for signal in fusion_input.signals),
    )
    final_snapshot = _apply_news_impact(base_snapshot, _news_impact_snapshot(fusion_input))
    explainability = _build_explainability(
        base_snapshot=base_snapshot,
        final_snapshot=final_snapshot,
        feature_scores=feature_scores,
        has_news=fusion_input.news_impact is not None and fusion_input.news_impact.item_count > 0,
    )
    return SignalFusionEngineResult(
        decision=final_snapshot.decision,
        confidence=final_snapshot.confidence,
        signal_count=final_snapshot.signal_count,
        regime=final_snapshot.regime,
        bullish_score=final_snapshot.bullish_score,
        bearish_score=final_snapshot.bearish_score,
        agreement=final_snapshot.agreement,
        latest_timestamp=final_snapshot.latest_timestamp,
        news_item_count=final_snapshot.news_item_count,
        news_bullish_score=final_snapshot.news_bullish_score,
        news_bearish_score=final_snapshot.news_bearish_score,
        explainability=explainability,
    )


def _news_impact_snapshot(fusion_input: SignalFusionInput) -> NewsImpactSnapshot | None:
    if fusion_input.news_impact is None:
        return None
    return NewsImpactSnapshot(
        item_count=fusion_input.news_impact.item_count,
        bullish_score=fusion_input.news_impact.bullish_score,
        bearish_score=fusion_input.news_impact.bearish_score,
        latest_timestamp=fusion_input.news_impact.latest_timestamp,
    )


def _build_explainability(
    *,
    base_snapshot: FusionSnapshot,
    final_snapshot: FusionSnapshot,
    feature_scores: dict[str, float],
    has_news: bool,
) -> SignalFusionExplainability:
    ordered_scores = tuple(
        SignalFusionFeatureScore(name=name, value=round(float(score), 6))
        for name, score in sorted(feature_scores.items(), key=lambda item: (-abs(item[1]), item[0]))
    )
    threshold_crossings: list[str] = []
    if base_snapshot.bullish_score + base_snapshot.bearish_score < WATCH_MIN_TOTAL_SCORE:
        threshold_crossings.append("below_watch_min_total_score")
    if has_news:
        threshold_crossings.append("news_impact_applied")
    if base_snapshot.decision != final_snapshot.decision:
        threshold_crossings.append("news_changed_decision")
    if final_snapshot.decision == "HOLD":
        threshold_crossings.append("balanced_directional_scores")
    if final_snapshot.agreement >= 0.5:
        threshold_crossings.append("strong_directional_agreement")
    if final_snapshot.confidence >= 0.75:
        threshold_crossings.append("high_confidence_threshold")
    return SignalFusionExplainability(
        dominant_factors=tuple(item.name for item in ordered_scores[:3]),
        threshold_crossings=tuple(threshold_crossings),
        feature_scores=ordered_scores,
        policy_path="signal_fusion/v1/news_adjusted" if has_news else "signal_fusion/v1/base",
    )


__all__ = ["resolve_signal_success_rate", "run_signal_fusion"]
