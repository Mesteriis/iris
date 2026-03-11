from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.cross_market_engine import cross_market_alignment_weight
from app.events.publisher import publish_event
from app.models.coin_metrics import CoinMetrics
from app.models.market_decision import MarketDecision
from app.models.pattern_statistic import PatternStatistic
from app.models.signal import Signal
from app.patterns.context import enrich_signal_context
from app.patterns.regime import read_regime_details
from app.patterns.semantics import is_cluster_signal, is_hierarchy_signal, pattern_bias, slug_from_signal_type
from app.services.decision_cache import cache_market_decision_snapshot
from app.services.market_data import ensure_utc

FUSION_SIGNAL_LIMIT = 20
FUSION_CANDLE_GROUPS = 3
WATCH_MIN_TOTAL_SCORE = 0.55
MATERIAL_CONFIDENCE_DELTA = 0.03

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


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _latest_decision(db: Session, coin_id: int, timeframe: int) -> MarketDecision | None:
    return db.scalar(
        select(MarketDecision)
        .where(MarketDecision.coin_id == coin_id, MarketDecision.timeframe == timeframe)
        .order_by(MarketDecision.created_at.desc(), MarketDecision.id.desc())
        .limit(1)
    )


def _recent_signals(db: Session, *, coin_id: int, timeframe: int) -> list[Signal]:
    rows = db.scalars(
        select(Signal)
        .where(Signal.coin_id == coin_id, Signal.timeframe == timeframe)
        .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc(), Signal.id.desc())
        .limit(FUSION_SIGNAL_LIMIT)
    ).all()
    if not rows:
        return []
    timestamps: list[datetime] = []
    selected: list[Signal] = []
    for row in rows:
        normalized = ensure_utc(row.candle_timestamp)
        if normalized not in timestamps:
            if len(timestamps) >= FUSION_CANDLE_GROUPS:
                break
            timestamps.append(normalized)
        if normalized in timestamps:
            selected.append(row)
    return selected


def _signal_regime(metrics: CoinMetrics | None, timeframe: int) -> str | None:
    if metrics is None:
        return None
    snapshot = read_regime_details(metrics.market_regime_details, timeframe)
    return snapshot.regime if snapshot is not None else metrics.market_regime


def _signal_success_rate(db: Session, signal: Signal, regime: str | None) -> float:
    slug = slug_from_signal_type(signal.signal_type)
    if slug is None:
        return 0.58 if is_cluster_signal(signal.signal_type) or is_hierarchy_signal(signal.signal_type) else 0.55
    row = db.scalar(
        select(PatternStatistic.success_rate)
        .where(
            PatternStatistic.pattern_slug == slug,
            PatternStatistic.timeframe == signal.timeframe,
            PatternStatistic.market_regime == (regime or "all"),
        )
        .limit(1)
    )
    if row is None and regime is not None:
        row = db.scalar(
            select(PatternStatistic.success_rate)
            .where(
                PatternStatistic.pattern_slug == slug,
                PatternStatistic.timeframe == signal.timeframe,
                PatternStatistic.market_regime == "all",
            )
            .limit(1)
        )
    return _clamp(float(row if row is not None else 0.55), 0.35, 0.95)


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


def _regime_weight(signal: Signal, regime: str | None) -> float:
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


def _weighted_signal_score(
    db: Session,
    *,
    signal: Signal,
    regime: str | None,
    age_index: int,
) -> float:
    success_rate = _signal_success_rate(db, signal, regime)
    context_factor = _clamp(float(signal.context_score or 1.0), 0.6, 1.4)
    alignment = _clamp(float(signal.regime_alignment or 1.0), 0.6, 1.4)
    priority_factor = _clamp(max(float(signal.priority_score or 0.0), float(signal.confidence)), 0.45, 1.6)
    directional_bias = pattern_bias(slug_from_signal_type(signal.signal_type) or signal.signal_type, fallback_price_delta=signal.confidence - 0.5)
    cross_market_factor = cross_market_alignment_weight(
        db,
        coin_id=int(signal.coin_id),
        timeframe=int(signal.timeframe),
        directional_bias=directional_bias,
    )
    recency_weight = max(1.0 - (age_index * 0.1), 0.75)
    return (
        _clamp(float(signal.confidence), 0.01, 1.0)
        * success_rate
        * _regime_weight(signal, regime)
        * context_factor
        * alignment
        * cross_market_factor
        * priority_factor
        * recency_weight
    )


def _decision_from_scores(*, bullish_score: float, bearish_score: float, total_score: float) -> tuple[str, float]:
    directional_score = bullish_score + bearish_score
    if directional_score <= 0 and total_score < WATCH_MIN_TOTAL_SCORE:
        return "WATCH", 0.2
    dominance = abs(bullish_score - bearish_score) / directional_score
    if bullish_score > 0 and bearish_score > 0 and dominance < 0.2:
        return "HOLD", _clamp(0.4 + (1.0 - dominance) * 0.3 + min(total_score / 4, 0.15), 0.35, 0.86)
    if total_score < WATCH_MIN_TOTAL_SCORE:
        return "WATCH", 0.22
    if dominance < 0.16:
        return "HOLD", _clamp(0.4 + (1.0 - dominance) * 0.3 + min(total_score / 4, 0.15), 0.35, 0.86)
    if bullish_score > bearish_score:
        return "BUY", _clamp(0.45 + dominance * 0.35 + min(total_score / 4, 0.22), 0.3, 0.96)
    return "SELL", _clamp(0.45 + dominance * 0.35 + min(total_score / 4, 0.22), 0.3, 0.96)


def _fuse_signals(db: Session, *, signals: list[Signal], regime: str | None) -> FusionSnapshot | None:
    if not signals:
        return None
    grouped_timestamps = sorted({ensure_utc(signal.candle_timestamp) for signal in signals}, reverse=True)
    age_by_timestamp = {timestamp: index for index, timestamp in enumerate(grouped_timestamps)}
    bullish_score = 0.0
    bearish_score = 0.0
    neutral_score = 0.0
    for signal in signals:
        age_index = age_by_timestamp[ensure_utc(signal.candle_timestamp)]
        score = _weighted_signal_score(db, signal=signal, regime=regime, age_index=age_index)
        slug = slug_from_signal_type(signal.signal_type) or signal.signal_type
        bias = pattern_bias(slug, fallback_price_delta=signal.confidence - 0.5)
        if bias > 0:
            bullish_score += score
        elif bias < 0:
            bearish_score += score
        else:
            neutral_score += score
    total_score = bullish_score + bearish_score + neutral_score
    decision, confidence = _decision_from_scores(
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        total_score=total_score,
    )
    agreement = abs(bullish_score - bearish_score) / max(bullish_score + bearish_score, 1e-9)
    if decision == "WATCH" and len(signals) >= 3 and total_score >= WATCH_MIN_TOTAL_SCORE:
        confidence = _clamp(confidence + 0.08, 0.22, 0.72)
    return FusionSnapshot(
        decision=decision,
        confidence=confidence,
        signal_count=len(signals),
        regime=regime,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        agreement=_clamp(agreement, 0.0, 1.0),
        latest_timestamp=max(ensure_utc(signal.candle_timestamp) for signal in signals),
    )


def evaluate_market_decision(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    trigger_timestamp: object | None = None,
    emit_event: bool = True,
) -> dict[str, object]:
    enrich_signal_context(
        db,
        coin_id=coin_id,
        timeframe=timeframe,
        candle_timestamp=trigger_timestamp,
        commit=True,
    )
    signals = _recent_signals(db, coin_id=coin_id, timeframe=timeframe)
    if not signals:
        return {"status": "skipped", "reason": "signals_not_found", "coin_id": coin_id, "timeframe": timeframe}

    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    regime = _signal_regime(metrics, timeframe)
    fused = _fuse_signals(db, signals=signals, regime=regime)
    if fused is None:
        return {"status": "skipped", "reason": "fusion_window_empty", "coin_id": coin_id, "timeframe": timeframe}

    latest = _latest_decision(db, coin_id, timeframe)
    if (
        latest is not None
        and latest.decision == fused.decision
        and latest.signal_count == fused.signal_count
        and abs(float(latest.confidence) - fused.confidence) < MATERIAL_CONFIDENCE_DELTA
    ):
        cache_market_decision_snapshot(
            coin_id=coin_id,
            timeframe=timeframe,
            decision=latest.decision,
            confidence=float(latest.confidence),
            signal_count=int(latest.signal_count),
            regime=regime,
            created_at=latest.created_at,
        )
        return {
            "status": "skipped",
            "reason": "decision_unchanged",
            "coin_id": coin_id,
            "timeframe": timeframe,
            "decision": latest.decision,
            "confidence": float(latest.confidence),
        }

    row = MarketDecision(
        coin_id=coin_id,
        timeframe=timeframe,
        decision=fused.decision,
        confidence=fused.confidence,
        signal_count=fused.signal_count,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    cache_market_decision_snapshot(
        coin_id=coin_id,
        timeframe=timeframe,
        decision=row.decision,
        confidence=float(row.confidence),
        signal_count=int(row.signal_count),
        regime=regime,
        created_at=row.created_at,
    )
    if emit_event:
        publish_event(
            "decision_generated",
            {
                "coin_id": coin_id,
                "timeframe": timeframe,
                "timestamp": fused.latest_timestamp,
                "decision": row.decision,
                "confidence": float(row.confidence),
                "signal_count": int(row.signal_count),
                "regime": regime,
                "source": "signal_fusion",
            },
        )
    return {
        "status": "ok",
        "id": row.id,
        "coin_id": coin_id,
        "timeframe": timeframe,
        "decision": row.decision,
        "confidence": float(row.confidence),
        "signal_count": int(row.signal_count),
        "regime": regime,
    }
