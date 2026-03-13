from __future__ import annotations

import logging
from datetime import datetime
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.apps.cross_market.engine import cross_market_alignment_weight
from src.apps.market_data.domain import ensure_utc
from src.apps.news.constants import NEWS_NORMALIZATION_STATUS_NORMALIZED
from src.apps.news.models import NewsItem, NewsItemLink
from src.apps.indicators.models import CoinMetrics
from src.apps.patterns.domain.context import enrich_signal_context
from src.apps.patterns.domain.semantics import is_cluster_signal, is_hierarchy_signal, pattern_bias, slug_from_signal_type
from src.apps.patterns.models import PatternStatistic
from src.apps.signals.cache import cache_market_decision_snapshot
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
from src.apps.signals.services import SignalFusionBatchResult, SignalFusionResult
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value
from src.runtime.streams.publisher import publish_event


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


class SignalFusionCompatibilityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        PERSISTENCE_LOGGER.log(
            level,
            event,
            extra={
                "persistence": {
                    "event": event,
                    "component_type": "compatibility_service",
                    "domain": "signals",
                    "component": "SignalFusionCompatibilityService",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def evaluate_news_fusion_event(
        self,
        *,
        coin_id: int,
        reference_timestamp: object | None = None,
        emit_event: bool = True,
    ) -> dict[str, object]:
        timeframes = _candidate_fusion_timeframes(self._db, coin_id=coin_id)
        if not timeframes:
            return SignalFusionBatchResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframes=(),
                items=(),
                reason="fusion_timeframes_not_found",
            ).to_summary()
        items = [
            self.evaluate_market_decision(
                coin_id=coin_id,
                timeframe=timeframe,
                trigger_timestamp=None,
                news_reference_timestamp=reference_timestamp,
                emit_event=emit_event,
            )
            for timeframe in timeframes
        ]
        return SignalFusionBatchResult(
            status="ok",
            coin_id=int(coin_id),
            timeframes=tuple(int(timeframe) for timeframe in timeframes),
            items=tuple(
                SignalFusionResult(
                    status=str(item["status"]),
                    coin_id=int(item["coin_id"]),
                    timeframe=int(item["timeframe"]),
                    reason=str(item["reason"]) if item.get("reason") is not None else None,
                    decision_id=int(item["id"]) if item.get("id") is not None else None,
                    decision=str(item["decision"]) if item.get("decision") is not None else None,
                    confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
                    signal_count=int(item.get("signal_count") or 0),
                    regime=str(item["regime"]) if item.get("regime") is not None else None,
                    news_item_count=int(item.get("news_item_count") or 0),
                    news_bullish_score=float(item.get("news_bullish_score") or 0.0),
                    news_bearish_score=float(item.get("news_bearish_score") or 0.0),
                )
                for item in items
            ),
        ).to_summary()

    def evaluate_market_decision(
        self,
        *,
        coin_id: int,
        timeframe: int,
        trigger_timestamp: object | None = None,
        news_reference_timestamp: object | None = None,
        emit_event: bool = True,
    ) -> dict[str, object]:
        enrich_signal_context(
            self._db,
            coin_id=coin_id,
            timeframe=timeframe,
            candle_timestamp=trigger_timestamp,
            commit=False,
        )
        signals = _recent_signals(self._db, coin_id=coin_id, timeframe=timeframe)
        if not signals:
            return SignalFusionResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="signals_not_found",
            ).to_summary()

        metrics = self._db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
        regime = _signal_regime(metrics, timeframe)
        reference_timestamp = ensure_utc(
            news_reference_timestamp or trigger_timestamp or max(signal.candle_timestamp for signal in signals)
        )
        fused_base = _fuse_signals(self._db, signals=signals, regime=regime)
        news_impact = _recent_news_impact(
            self._db,
            coin_id=coin_id,
            timeframe=timeframe,
            reference_timestamp=reference_timestamp,
        )
        fused = _apply_news_impact(fused_base, news_impact) if fused_base is not None else None
        if fused is None:
            self._db.commit()
            return SignalFusionResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="fusion_window_empty",
            ).to_summary()

        latest = _latest_decision(self._db, coin_id, timeframe)
        if (
            latest is not None
            and latest.decision == fused.decision
            and latest.signal_count == fused.signal_count
            and abs(float(latest.confidence) - fused.confidence) < MATERIAL_CONFIDENCE_DELTA
        ):
            self._db.commit()
            cache_market_decision_snapshot(
                coin_id=coin_id,
                timeframe=timeframe,
                decision=latest.decision,
                confidence=float(latest.confidence),
                signal_count=int(latest.signal_count),
                regime=regime,
                created_at=latest.created_at,
            )
            return SignalFusionResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="decision_unchanged",
                decision_id=int(latest.id),
                decision=str(latest.decision),
                confidence=float(latest.confidence),
                signal_count=int(latest.signal_count),
                regime=regime,
                news_item_count=int(fused.news_item_count),
                news_bullish_score=float(fused.news_bullish_score),
                news_bearish_score=float(fused.news_bearish_score),
            ).to_summary()

        row = MarketDecision(
            coin_id=coin_id,
            timeframe=timeframe,
            decision=fused.decision,
            confidence=fused.confidence,
            signal_count=fused.signal_count,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
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
        return SignalFusionResult(
            status="ok",
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            decision_id=int(row.id),
            decision=str(row.decision),
            confidence=float(row.confidence),
            signal_count=int(row.signal_count),
            regime=regime,
            news_item_count=int(fused.news_item_count),
            news_bullish_score=float(fused.news_bullish_score),
            news_bearish_score=float(fused.news_bearish_score),
        ).to_summary()


def evaluate_news_fusion_event(
    db: Session,
    *,
    coin_id: int,
    reference_timestamp: object | None = None,
    emit_event: bool = True,
) -> dict[str, object]:
    service = SignalFusionCompatibilityService(db)
    service._log(
        logging.WARNING,
        "compat.evaluate_news_fusion_event.deprecated",
        mode="write",
        coin_id=coin_id,
        emit_event=emit_event,
    )
    return service.evaluate_news_fusion_event(
        coin_id=coin_id,
        reference_timestamp=reference_timestamp,
        emit_event=emit_event,
    )


def evaluate_market_decision(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    trigger_timestamp: object | None = None,
    news_reference_timestamp: object | None = None,
    emit_event: bool = True,
) -> dict[str, object]:
    service = SignalFusionCompatibilityService(db)
    service._log(
        logging.WARNING,
        "compat.evaluate_market_decision.deprecated",
        mode="write",
        coin_id=coin_id,
        timeframe=timeframe,
        emit_event=emit_event,
    )
    return service.evaluate_market_decision(
        coin_id=coin_id,
        timeframe=timeframe,
        trigger_timestamp=trigger_timestamp,
        news_reference_timestamp=news_reference_timestamp,
        emit_event=emit_event,
    )


__all__ = [
    "SignalFusionCompatibilityService",
    "evaluate_market_decision",
    "evaluate_news_fusion_event",
]
