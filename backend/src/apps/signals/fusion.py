from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.apps.cross_market.engine import cross_market_alignment_weight
from src.apps.market_data.domain import ensure_utc
from src.apps.news.constants import NEWS_NORMALIZATION_STATUS_NORMALIZED
from src.apps.news.models import NewsItem, NewsItemLink
from src.apps.patterns.domain.semantics import is_cluster_signal, is_hierarchy_signal, pattern_bias, slug_from_signal_type
from src.apps.patterns.models import PatternStatistic
from src.apps.signals.fusion_support import (
    FUSION_CANDLE_GROUPS,
    FUSION_NEWS_TIMEFRAMES,
    FUSION_SIGNAL_LIMIT,
    FusionSnapshot,
    MATERIAL_CONFIDENCE_DELTA,
    NEWS_FUSION_MAX_ITEMS,
    NEWS_FUSION_SCORE_CAP,
    NewsImpactSnapshot,
    _apply_news_impact,
    _clamp,
    _decision_from_scores,
    _regime_weight,
    _signal_archetype,
    _signal_regime,
)
from src.apps.signals.models import MarketDecision, Signal


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
