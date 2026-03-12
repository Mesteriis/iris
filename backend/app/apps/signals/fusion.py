from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.apps.cross_market.engine import cross_market_alignment_weight
from app.apps.news.constants import NEWS_NORMALIZATION_STATUS_NORMALIZED
from app.apps.news.models import NewsItem, NewsItemLink
from app.runtime.streams.publisher import publish_event
from app.apps.indicators.models import CoinMetrics
from app.apps.signals.models import MarketDecision
from app.apps.patterns.models import PatternStatistic
from app.apps.signals.models import Signal
from app.apps.patterns.domain.context import enrich_signal_context
from app.apps.patterns.domain.regime import read_regime_details
from app.apps.patterns.domain.semantics import is_cluster_signal, is_hierarchy_signal, pattern_bias, slug_from_signal_type
from app.apps.signals.cache import cache_market_decision_snapshot
from app.apps.market_data.domain import ensure_utc

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
    if bullish_score > bearish_score:
        return "BUY", _clamp(0.45 + dominance * 0.35 + min(total_score / 4, 0.22), 0.3, 0.96)
    return "SELL", _clamp(0.45 + dominance * 0.35 + min(total_score / 4, 0.22), 0.3, 0.96)


def _news_lookback(timeframe: int) -> timedelta:
    if timeframe <= 15:
        return timedelta(hours=12)
    if timeframe <= 60:
        return timedelta(hours=24)
    if timeframe <= 240:
        return timedelta(hours=48)
    return timedelta(days=7)


def _recent_news_impact(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    reference_timestamp: datetime,
) -> NewsImpactSnapshot | None:
    lookback = _news_lookback(timeframe)
    since = reference_timestamp - lookback
    rows = (
        db.execute(
            select(
                NewsItem.id,
                NewsItem.published_at,
                NewsItem.sentiment_score,
                NewsItem.relevance_score,
                NewsItemLink.confidence,
            )
            .join(NewsItemLink, NewsItemLink.news_item_id == NewsItem.id)
            .where(
                NewsItemLink.coin_id == coin_id,
                NewsItem.normalization_status == NEWS_NORMALIZATION_STATUS_NORMALIZED,
                NewsItem.published_at >= since,
                NewsItem.published_at <= reference_timestamp,
            )
            .order_by(NewsItem.published_at.desc(), NewsItemLink.confidence.desc())
            .limit(NEWS_FUSION_MAX_ITEMS)
        )
    ).all()
    if not rows:
        return None

    bullish_score = 0.0
    bearish_score = 0.0
    latest_timestamp = max(ensure_utc(row.published_at) for row in rows)
    lookback_seconds = max(lookback.total_seconds(), 1.0)
    for row in rows:
        published_at = ensure_utc(row.published_at)
        age_seconds = max((reference_timestamp - published_at).total_seconds(), 0.0)
        recency_weight = _clamp(1.0 - (age_seconds / lookback_seconds), 0.12, 1.0)
        base_weight = (
            _clamp(float(row.confidence or 0.0), 0.0, 1.0)
            * _clamp(float(row.relevance_score or 0.0), 0.0, 1.0)
            * recency_weight
        )
        sentiment = float(row.sentiment_score or 0.0)
        if sentiment >= 0.08:
            bullish_score += base_weight * max(abs(sentiment), 0.2)
        elif sentiment <= -0.08:
            bearish_score += base_weight * max(abs(sentiment), 0.2)
        else:
            bullish_score += base_weight * 0.05
            bearish_score += base_weight * 0.05
    return NewsImpactSnapshot(
        item_count=len(rows),
        bullish_score=round(_clamp(bullish_score, 0.0, NEWS_FUSION_SCORE_CAP), 4),
        bearish_score=round(_clamp(bearish_score, 0.0, NEWS_FUSION_SCORE_CAP), 4),
        latest_timestamp=latest_timestamp,
    )


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


def _candidate_fusion_timeframes(db: Session, *, coin_id: int) -> list[int]:
    rows = db.scalars(
        select(Signal.timeframe)
        .where(Signal.coin_id == coin_id, Signal.timeframe.in_(FUSION_NEWS_TIMEFRAMES))
        .distinct()
    ).all()
    available = {int(row) for row in rows if int(row) > 0}
    return [timeframe for timeframe in FUSION_NEWS_TIMEFRAMES if timeframe in available]


def _fuse_signals(db: Session, *, signals: list[Signal], regime: str | None) -> FusionSnapshot | None:
    if not signals:
        return None
    grouped_timestamps = sorted({ensure_utc(signal.candle_timestamp) for signal in signals}, reverse=True)
    age_by_timestamp = {timestamp: index for index, timestamp in enumerate(grouped_timestamps)}
    bullish_score = 0.0
    bearish_score = 0.0
    for signal in signals:
        age_index = age_by_timestamp[ensure_utc(signal.candle_timestamp)]
        score = _weighted_signal_score(db, signal=signal, regime=regime, age_index=age_index)
        slug = slug_from_signal_type(signal.signal_type) or signal.signal_type
        bias = pattern_bias(slug, fallback_price_delta=signal.confidence - 0.5)
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


def evaluate_news_fusion_event(
    db: Session,
    *,
    coin_id: int,
    reference_timestamp: object | None = None,
    emit_event: bool = True,
) -> dict[str, object]:
    timeframes = _candidate_fusion_timeframes(db, coin_id=coin_id)
    if not timeframes:
        return {"status": "skipped", "reason": "fusion_timeframes_not_found", "coin_id": coin_id}
    items = [
        evaluate_market_decision(
            db,
            coin_id=coin_id,
            timeframe=timeframe,
            trigger_timestamp=None,
            news_reference_timestamp=reference_timestamp,
            emit_event=emit_event,
        )
        for timeframe in timeframes
    ]
    return {
        "status": "ok",
        "coin_id": coin_id,
        "timeframes": timeframes,
        "items": items,
    }


def evaluate_market_decision(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    trigger_timestamp: object | None = None,
    news_reference_timestamp: object | None = None,
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
    reference_timestamp = ensure_utc(news_reference_timestamp or trigger_timestamp or max(signal.candle_timestamp for signal in signals))
    fused_base = _fuse_signals(db, signals=signals, regime=regime)
    news_impact = _recent_news_impact(
        db,
        coin_id=coin_id,
        timeframe=timeframe,
        reference_timestamp=reference_timestamp,
    )
    fused = _apply_news_impact(fused_base, news_impact) if fused_base is not None else None
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
            "news_item_count": fused.news_item_count,
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
                "news_item_count": int(fused.news_item_count),
                "news_bullish_score": round(float(fused.news_bullish_score), 4),
                "news_bearish_score": round(float(fused.news_bearish_score), 4),
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
        "news_item_count": int(fused.news_item_count),
        "news_bullish_score": round(float(fused.news_bullish_score), 4),
        "news_bearish_score": round(float(fused.news_bearish_score), 4),
    }
