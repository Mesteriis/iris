from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta

from src.apps.cross_market.cache import read_cached_correlation_async
from src.apps.market_data.domain import ensure_utc
from src.apps.market_data.repositories import CandleRepository
from src.apps.patterns.domain.context import enrich_signal_context
from src.apps.patterns.domain.semantics import is_cluster_signal, is_hierarchy_signal, pattern_bias, slug_from_signal_type
from src.apps.signals.backtests import get_coin_backtests, list_backtests, list_top_backtests
from src.apps.signals.cache import cache_market_decision_snapshot_async
from src.apps.signals.decision_selectors import get_coin_decision, list_decisions, list_top_decisions
from src.apps.signals.final_signal_selectors import get_coin_final_signal, list_final_signals, list_top_final_signals
from src.apps.signals.fusion import (
    FUSION_CANDLE_GROUPS,
    FUSION_NEWS_TIMEFRAMES,
    FUSION_SIGNAL_LIMIT,
    MATERIAL_CONFIDENCE_DELTA,
    NEWS_FUSION_MAX_ITEMS,
    FusionSnapshot,
    NewsImpactSnapshot,
    _apply_news_impact,
    _clamp,
    _decision_from_scores,
    _regime_weight,
    _signal_regime,
    evaluate_market_decision,
    evaluate_news_fusion_event,
)
from src.apps.signals.history import refresh_recent_signal_history, refresh_signal_history
from src.apps.signals.market_decision_selectors import (
    get_coin_market_decision,
    list_market_decisions,
    list_top_market_decisions,
)
from src.apps.signals.models import MarketDecision, Signal
from src.apps.signals.repositories import SignalFusionRepository, SignalHistoryRepository
from src.apps.signals.strategies import list_strategies, list_strategy_performance
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.publisher import publish_event
from src.apps.signals.history import (
    SIGNAL_HISTORY_LOOKBACK_DAYS,
    SIGNAL_HISTORY_RECENT_LIMIT,
    _close_timestamps,
    _evaluate_signal,
    _open_timestamp_from_signal,
)


@dataclass(slots=True, frozen=True)
class SignalDecisionCacheSnapshot:
    coin_id: int
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None
    created_at: datetime | None


@dataclass(slots=True, frozen=True)
class SignalFusionPendingEvent:
    event_type: str
    payload: dict[str, object]


@dataclass(slots=True, frozen=True)
class SignalFusionResult:
    status: str
    coin_id: int
    timeframe: int
    reason: str | None = None
    decision_id: int | None = None
    decision: str | None = None
    confidence: float | None = None
    signal_count: int = 0
    regime: str | None = None
    news_item_count: int = 0
    news_bullish_score: float = 0.0
    news_bearish_score: float = 0.0
    cache_snapshot: SignalDecisionCacheSnapshot | None = None
    pending_events: tuple[SignalFusionPendingEvent, ...] = ()

    def to_summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "coin_id": self.coin_id,
            "timeframe": self.timeframe,
            "signal_count": self.signal_count,
            "news_item_count": self.news_item_count,
            "news_bullish_score": round(float(self.news_bullish_score), 4),
            "news_bearish_score": round(float(self.news_bearish_score), 4),
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.decision_id is not None:
            payload["id"] = self.decision_id
        if self.decision is not None:
            payload["decision"] = self.decision
        if self.confidence is not None:
            payload["confidence"] = float(self.confidence)
        if self.regime is not None:
            payload["regime"] = self.regime
        return payload


@dataclass(slots=True, frozen=True)
class SignalFusionBatchResult:
    status: str
    coin_id: int
    timeframes: tuple[int, ...]
    items: tuple[SignalFusionResult, ...]
    reason: str | None = None

    def to_summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "coin_id": self.coin_id,
            "timeframes": list(self.timeframes),
            "items": [item.to_summary() for item in self.items],
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(slots=True, frozen=True)
class SignalHistoryRefreshResult:
    status: str
    rows: int
    evaluated: int
    coin_id: int | None
    timeframe: int | None

    def to_summary(self) -> dict[str, object]:
        return {
            "status": self.status,
            "rows": self.rows,
            "evaluated": self.evaluated,
            "coin_id": self.coin_id,
            "timeframe": self.timeframe,
        }


class SignalFusionSideEffectDispatcher:
    async def apply(self, result: SignalFusionResult | SignalFusionBatchResult) -> None:
        if isinstance(result, SignalFusionBatchResult):
            for item in result.items:
                await self.apply(item)
            return
        if result.cache_snapshot is not None:
            await cache_market_decision_snapshot_async(
                coin_id=result.cache_snapshot.coin_id,
                timeframe=result.cache_snapshot.timeframe,
                decision=result.cache_snapshot.decision,
                confidence=result.cache_snapshot.confidence,
                signal_count=result.cache_snapshot.signal_count,
                regime=result.cache_snapshot.regime,
                created_at=result.cache_snapshot.created_at,
            )
        for event in result.pending_events:
            publish_event(event.event_type, event.payload)


class SignalFusionService(PersistenceComponent):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="signals",
            component_name="SignalFusionService",
        )
        self._uow = uow
        self._signals = SignalFusionRepository(uow.session)

    async def evaluate_news_fusion_event(
        self,
        *,
        coin_id: int,
        reference_timestamp: object | None = None,
        emit_event: bool = True,
    ) -> SignalFusionBatchResult:
        self._log_debug(
            "service.evaluate_news_fusion_event",
            mode="write",
            coin_id=coin_id,
            emit_event=emit_event,
        )
        timeframes = await self._signals.list_candidate_fusion_timeframes(
            coin_id=int(coin_id),
            allowed_timeframes=FUSION_NEWS_TIMEFRAMES,
        )
        if not timeframes:
            self._log_debug(
                "service.evaluate_news_fusion_event.result",
                mode="write",
                coin_id=coin_id,
                status="skipped",
                reason="fusion_timeframes_not_found",
            )
            return SignalFusionBatchResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframes=(),
                items=(),
                reason="fusion_timeframes_not_found",
            )
        items_list: list[SignalFusionResult] = []
        for timeframe in timeframes:
            items_list.append(
                await self.evaluate_market_decision(
                    coin_id=int(coin_id),
                    timeframe=int(timeframe),
                    trigger_timestamp=None,
                    news_reference_timestamp=reference_timestamp,
                    emit_event=emit_event,
                )
            )
        self._log_info(
            "service.evaluate_news_fusion_event.result",
            mode="write",
            coin_id=coin_id,
            timeframes=len(timeframes),
        )
        return SignalFusionBatchResult(
            status="ok",
            coin_id=int(coin_id),
            timeframes=tuple(int(item) for item in timeframes),
            items=tuple(items_list),
        )

    async def evaluate_market_decision(
        self,
        *,
        coin_id: int,
        timeframe: int,
        trigger_timestamp: object | None = None,
        news_reference_timestamp: object | None = None,
        emit_event: bool = True,
    ) -> SignalFusionResult:
        self._log_debug(
            "service.evaluate_market_decision",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            emit_event=emit_event,
        )
        await self._enrich_context(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            candle_timestamp=trigger_timestamp,
        )
        signals = await self._recent_signals(coin_id=int(coin_id), timeframe=int(timeframe))
        if not signals:
            self._log_debug(
                "service.evaluate_market_decision.result",
                mode="write",
                coin_id=coin_id,
                timeframe=timeframe,
                status="skipped",
                reason="signals_not_found",
            )
            return SignalFusionResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="signals_not_found",
            )

        metrics = await self._signals.get_coin_metrics(coin_id=int(coin_id))
        regime = _signal_regime(metrics, int(timeframe))
        reference_timestamp = ensure_utc(
            news_reference_timestamp or trigger_timestamp or max(signal.candle_timestamp for signal in signals)
        )
        success_rates = await self._pattern_success_rates(signals=signals, timeframe=int(timeframe), regime=regime)
        bullish_alignment = await self._cross_market_alignment_weight(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            directional_bias=1.0,
        )
        bearish_alignment = await self._cross_market_alignment_weight(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            directional_bias=-1.0,
        )
        fused_base = self._fuse_signals(
            signals=signals,
            regime=regime,
            success_rates=success_rates,
            bullish_alignment=bullish_alignment,
            bearish_alignment=bearish_alignment,
        )
        news_impact = await self._recent_news_impact(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            reference_timestamp=reference_timestamp,
        )
        fused = _apply_news_impact(fused_base, news_impact) if fused_base is not None else None
        if fused is None:
            self._log_debug(
                "service.evaluate_market_decision.result",
                mode="write",
                coin_id=coin_id,
                timeframe=timeframe,
                status="skipped",
                reason="fusion_window_empty",
            )
            return SignalFusionResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="fusion_window_empty",
            )

        latest = await self._signals.get_latest_market_decision(coin_id=int(coin_id), timeframe=int(timeframe))
        if (
            latest is not None
            and latest.decision == fused.decision
            and int(latest.signal_count) == fused.signal_count
            and abs(float(latest.confidence) - fused.confidence) < MATERIAL_CONFIDENCE_DELTA
        ):
            self._log_debug(
                "service.evaluate_market_decision.result",
                mode="write",
                coin_id=coin_id,
                timeframe=timeframe,
                status="skipped",
                reason="decision_unchanged",
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
                cache_snapshot=SignalDecisionCacheSnapshot(
                    coin_id=int(coin_id),
                    timeframe=int(timeframe),
                    decision=str(latest.decision),
                    confidence=float(latest.confidence),
                    signal_count=int(latest.signal_count),
                    regime=regime,
                    created_at=latest.created_at,
                ),
            )

        row = await self._signals.add_market_decision(
            MarketDecision(
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                decision=fused.decision,
                confidence=fused.confidence,
                signal_count=fused.signal_count,
            )
        )
        pending_events: tuple[SignalFusionPendingEvent, ...] = ()
        if emit_event:
            pending_events = (
                SignalFusionPendingEvent(
                    "decision_generated",
                    {
                        "coin_id": int(coin_id),
                        "timeframe": int(timeframe),
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
                ),
            )
        result = SignalFusionResult(
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
            cache_snapshot=SignalDecisionCacheSnapshot(
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                decision=str(row.decision),
                confidence=float(row.confidence),
                signal_count=int(row.signal_count),
                regime=regime,
                created_at=row.created_at,
            ),
            pending_events=pending_events,
        )
        self._log_info(
            "service.evaluate_market_decision.result",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            decision=result.decision,
            signal_count=result.signal_count,
        )
        return result

    async def _enrich_context(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None,
    ) -> None:
        self._log_debug(
            "service.evaluate_market_decision.context_adapter",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            compatibility_path="patterns.domain.context.enrich_signal_context",
        )
        await self.session.run_sync(
            lambda db: enrich_signal_context(
                db,
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                candle_timestamp=candle_timestamp,
                commit=False,
            )
        )

    async def _recent_signals(self, *, coin_id: int, timeframe: int) -> list[Signal]:
        rows = await self._signals.list_recent_signals(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            limit=FUSION_SIGNAL_LIMIT,
        )
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

    async def _pattern_success_rates(
        self,
        *,
        signals: list[Signal],
        timeframe: int,
        regime: str | None,
    ) -> dict[tuple[str, str], float]:
        slugs = sorted(
            {
                slug
                for signal in signals
                if (slug := slug_from_signal_type(str(signal.signal_type))) is not None
            }
        )
        regimes = ["all"]
        if regime is not None:
            regimes.insert(0, str(regime))
        return await self._signals.list_pattern_success_rates(
            timeframe=int(timeframe),
            pattern_slugs=slugs,
            market_regimes=regimes,
        )

    async def _cross_market_alignment_weight(
        self,
        *,
        coin_id: int,
        timeframe: int,
        directional_bias: float,
    ) -> float:
        if directional_bias == 0:
            return 1.0
        relations = await self._signals.list_alignment_relations(follower_coin_id=int(coin_id), limit=3)
        if not relations:
            return 1.0
        leader_decisions = await self._signals.list_latest_leader_decisions(
            leader_coin_ids=[int(item.leader_coin_id) for item in relations],
            timeframe=int(timeframe),
        )
        weight = 1.0
        for relation in relations:
            cached = await read_cached_correlation_async(
                leader_coin_id=int(relation.leader_coin_id),
                follower_coin_id=int(relation.follower_coin_id),
            )
            decision, decision_confidence = leader_decisions.get(int(relation.leader_coin_id), (None, 0.0))
            if decision is None:
                continue
            relation_strength = float(cached.confidence if cached is not None else relation.confidence) * float(
                cached.correlation if cached is not None else relation.correlation
            )
            delta = min(relation_strength * max(float(decision_confidence), 0.3), 0.22)
            if directional_bias > 0 and decision == "BUY":
                weight += delta
            elif directional_bias < 0 and decision == "SELL":
                weight += delta
            elif decision in {"BUY", "SELL"}:
                weight -= delta * 0.8
        sector_trend = await self._signals.get_sector_trend(coin_id=int(coin_id), timeframe=int(timeframe))
        if sector_trend is not None:
            if directional_bias > 0 and sector_trend == "bullish":
                weight += 0.05
            elif directional_bias < 0 and sector_trend == "bearish":
                weight += 0.05
            elif sector_trend in {"bullish", "bearish"}:
                weight -= 0.04
        return _clamp(weight, 0.75, 1.35)

    async def _recent_news_impact(
        self,
        *,
        coin_id: int,
        timeframe: int,
        reference_timestamp: datetime,
    ) -> NewsImpactSnapshot | None:
        lookback = self._news_lookback(int(timeframe))
        since = reference_timestamp - lookback
        rows = await self._signals.list_recent_news_rows(
            coin_id=int(coin_id),
            reference_timestamp=reference_timestamp,
            since=since,
            limit=NEWS_FUSION_MAX_ITEMS,
        )
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
            bullish_score=round(_clamp(bullish_score, 0.0, 0.85), 4),
            bearish_score=round(_clamp(bearish_score, 0.0, 0.85), 4),
            latest_timestamp=latest_timestamp,
        )

    @staticmethod
    def _news_lookback(timeframe: int) -> timedelta:
        if timeframe <= 15:
            return timedelta(hours=12)
        if timeframe <= 60:
            return timedelta(hours=24)
        if timeframe <= 240:
            return timedelta(hours=48)
        return timedelta(days=7)

    def _fuse_signals(
        self,
        *,
        signals: list[Signal],
        regime: str | None,
        success_rates: dict[tuple[str, str], float],
        bullish_alignment: float,
        bearish_alignment: float,
    ) -> FusionSnapshot | None:
        if not signals:
            return None
        grouped_timestamps = sorted({ensure_utc(signal.candle_timestamp) for signal in signals}, reverse=True)
        age_by_timestamp = {timestamp: index for index, timestamp in enumerate(grouped_timestamps)}
        bullish_score = 0.0
        bearish_score = 0.0
        for signal in signals:
            age_index = age_by_timestamp[ensure_utc(signal.candle_timestamp)]
            slug = slug_from_signal_type(str(signal.signal_type))
            success_rate = self._signal_success_rate(
                signal=signal,
                slug=slug,
                regime=regime,
                success_rates=success_rates,
            )
            context_factor = _clamp(float(signal.context_score or 1.0), 0.6, 1.4)
            alignment = _clamp(float(signal.regime_alignment or 1.0), 0.6, 1.4)
            priority_factor = _clamp(max(float(signal.priority_score or 0.0), float(signal.confidence)), 0.45, 1.6)
            bias = pattern_bias(slug or str(signal.signal_type), fallback_price_delta=float(signal.confidence) - 0.5)
            cross_market_factor = bullish_alignment if bias > 0 else bearish_alignment
            recency_weight = max(1.0 - (age_index * 0.1), 0.75)
            score = (
                _clamp(float(signal.confidence), 0.01, 1.0)
                * success_rate
                * _regime_weight(signal, regime)
                * context_factor
                * alignment
                * cross_market_factor
                * priority_factor
                * recency_weight
            )
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

    @staticmethod
    def _signal_success_rate(
        *,
        signal: Signal,
        slug: str | None,
        regime: str | None,
        success_rates: dict[tuple[str, str], float],
    ) -> float:
        if slug is None:
            if is_cluster_signal(str(signal.signal_type)) or is_hierarchy_signal(str(signal.signal_type)):
                return 0.58
            return 0.55
        if regime is not None and (slug, regime) in success_rates:
            return _clamp(float(success_rates[(slug, regime)]), 0.35, 0.95)
        if (slug, "all") in success_rates:
            return _clamp(float(success_rates[(slug, "all")]), 0.35, 0.95)
        return 0.55


class SignalHistoryService(PersistenceComponent):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="signals",
            component_name="SignalHistoryService",
        )
        self._history = SignalHistoryRepository(uow.session)
        self._candles = CandleRepository(uow.session)

    async def refresh_history(
        self,
        *,
        lookback_days: int = SIGNAL_HISTORY_LOOKBACK_DAYS,
        coin_id: int | None = None,
        timeframe: int | None = None,
        limit_per_scope: int | None = None,
    ) -> SignalHistoryRefreshResult:
        self._log_debug(
            "service.refresh_signal_history",
            mode="write",
            lookback_days=lookback_days,
            coin_id=coin_id,
            timeframe=timeframe,
            limit_per_scope=limit_per_scope,
        )
        signals = await self._history.list_signals_for_history(
            lookback_days=int(lookback_days),
            coin_id=coin_id,
            timeframe=timeframe,
            limit_per_scope=limit_per_scope,
        )
        if not signals:
            self._log_debug(
                "service.refresh_signal_history.result",
                mode="write",
                status="ok",
                rows=0,
                evaluated=0,
                coin_id=coin_id,
                timeframe=timeframe,
            )
            return SignalHistoryRefreshResult(
                status="ok",
                rows=0,
                evaluated=0,
                coin_id=coin_id,
                timeframe=timeframe,
            )

        groups: dict[tuple[int, int], list[Signal]] = {}
        for signal in signals:
            groups.setdefault((int(signal.coin_id), int(signal.timeframe)), []).append(signal)

        rows: list[dict[str, object]] = []
        evaluated = 0
        for (group_coin_id, group_timeframe), scoped_signals in groups.items():
            if not scoped_signals:
                continue
            start = _open_timestamp_from_signal(scoped_signals[0])
            end = ensure_utc(scoped_signals[-1].candle_timestamp) + timedelta(hours=72, minutes=group_timeframe)
            candles = await self._candles.fetch_points_between(
                coin_id=group_coin_id,
                timeframe=group_timeframe,
                window_start=start,
                window_end=end,
            )
            if not candles:
                self._log_debug(
                    "service.refresh_signal_history.group_missing_candles",
                    mode="write",
                    coin_id=group_coin_id,
                    timeframe=group_timeframe,
                    signal_count=len(scoped_signals),
                )
                rows.extend(
                    {
                        "coin_id": signal.coin_id,
                        "timeframe": signal.timeframe,
                        "signal_type": signal.signal_type,
                        "confidence": float(signal.confidence),
                        "market_regime": signal.market_regime,
                        "candle_timestamp": signal.candle_timestamp,
                        "profit_after_24h": None,
                        "profit_after_72h": None,
                        "maximum_drawdown": None,
                        "result_return": None,
                        "result_drawdown": None,
                        "evaluated_at": None,
                    }
                    for signal in scoped_signals
                )
                continue

            close_timestamps = _close_timestamps(candles, group_timeframe)
            close_index_map = {timestamp: index for index, timestamp in enumerate(close_timestamps)}
            for signal in scoped_signals:
                outcome = _evaluate_signal(signal, candles, close_timestamps, close_index_map)
                if outcome.evaluated_at is not None:
                    evaluated += 1
                rows.append(
                    {
                        "coin_id": signal.coin_id,
                        "timeframe": signal.timeframe,
                        "signal_type": signal.signal_type,
                        "confidence": float(signal.confidence),
                        "market_regime": signal.market_regime,
                        "candle_timestamp": signal.candle_timestamp,
                        "profit_after_24h": outcome.profit_after_24h,
                        "profit_after_72h": outcome.profit_after_72h,
                        "maximum_drawdown": outcome.maximum_drawdown,
                        "result_return": outcome.result_return,
                        "result_drawdown": outcome.result_drawdown,
                        "evaluated_at": outcome.evaluated_at,
                    }
                )
        await self._history.upsert_signal_history(rows=rows)
        result = SignalHistoryRefreshResult(
            status="ok",
            rows=len(rows),
            evaluated=evaluated,
            coin_id=coin_id,
            timeframe=timeframe,
        )
        self._log_info(
            "service.refresh_signal_history.result",
            mode="write",
            rows=result.rows,
            evaluated=result.evaluated,
            coin_id=coin_id,
            timeframe=timeframe,
        )
        return result

    async def refresh_recent_history(
        self,
        *,
        coin_id: int,
        timeframe: int,
    ) -> SignalHistoryRefreshResult:
        self._log_debug(
            "service.refresh_recent_signal_history",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        return await self.refresh_history(
            lookback_days=SIGNAL_HISTORY_LOOKBACK_DAYS,
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            limit_per_scope=SIGNAL_HISTORY_RECENT_LIMIT,
        )


__all__ = [
    "SignalDecisionCacheSnapshot",
    "SignalFusionBatchResult",
    "SignalFusionPendingEvent",
    "SignalFusionResult",
    "SignalFusionService",
    "SignalFusionSideEffectDispatcher",
    "SignalHistoryRefreshResult",
    "SignalHistoryService",
    "evaluate_market_decision",
    "evaluate_news_fusion_event",
    "get_coin_backtests",
    "get_coin_decision",
    "get_coin_final_signal",
    "get_coin_market_decision",
    "list_backtests",
    "list_decisions",
    "list_final_signals",
    "list_market_decisions",
    "list_strategies",
    "list_strategy_performance",
    "list_top_backtests",
    "list_top_decisions",
    "list_top_final_signals",
    "list_top_market_decisions",
    "refresh_recent_signal_history",
    "refresh_signal_history",
]
