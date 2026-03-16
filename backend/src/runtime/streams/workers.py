import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from src.apps.anomalies.consumers import CandleAnomalyConsumer, SectorAnomalyConsumer
from src.apps.control_plane.metrics import ControlPlaneMetricsStore
from src.apps.cross_market.services import CrossMarketService
from src.apps.hypothesis_engine.consumers import HypothesisConsumer
from src.apps.indicators.results import IndicatorEventResult
from src.apps.indicators.services import AnalysisSchedulerService, FeatureSnapshotService, IndicatorAnalyticsService
from src.apps.news.consumers import NewsCorrelationConsumer, NewsNormalizationConsumer
from src.apps.notifications.consumers import NotificationConsumer
from src.apps.patterns.cache import cache_regime_snapshot_async, read_cached_regime_async
from src.apps.patterns.runtime_results import PatternRegimeRefreshResult
from src.apps.portfolio.services import PortfolioService, PortfolioSideEffectDispatcher
from src.apps.signals.services import SignalFusionService, SignalFusionSideEffectDispatcher, SignalHistoryService
from src.apps.signals.services.results import SignalFusionBatchResult, SignalFusionResult
from src.core.db.uow import AsyncUnitOfWork, BaseAsyncUnitOfWork
from src.core.settings import get_settings
from src.runtime.control_plane.worker import build_delivery_stream_name
from src.runtime.streams.consumer import EventConsumer, EventConsumerConfig, default_consumer_name
from src.runtime.streams.publisher import publish_event
from src.runtime.streams.types import (
    ANALYSIS_SCHEDULER_WORKER_GROUP,
    ANOMALY_SECTOR_WORKER_GROUP,
    ANOMALY_WORKER_GROUP,
    CROSS_MARKET_WORKER_GROUP,
    DECISION_WORKER_GROUP,
    FUSION_WORKER_GROUP,
    HYPOTHESIS_WORKER_GROUP,
    INDICATOR_WORKER_GROUP,
    NEWS_CORRELATION_WORKER_GROUP,
    NEWS_NORMALIZATION_WORKER_GROUP,
    NOTIFICATION_WORKER_GROUP,
    PATTERN_WORKER_GROUP,
    PORTFOLIO_WORKER_GROUP,
    REGIME_WORKER_GROUP,
    IrisEvent,
)

LOGGER = logging.getLogger(__name__)
_ANOMALY_CONSUMER = CandleAnomalyConsumer()
_ANOMALY_SECTOR_CONSUMER = SectorAnomalyConsumer()
_NEWS_NORMALIZATION_CONSUMER = NewsNormalizationConsumer()
_NEWS_CORRELATION_CONSUMER = NewsCorrelationConsumer()
_HYPOTHESIS_CONSUMER = HypothesisConsumer()
_NOTIFICATION_CONSUMER = NotificationConsumer()
_CONTROL_PLANE_METRICS = ControlPlaneMetricsStore()
_PATTERN_INTERESTED_EVENT_TYPES = frozenset({"analysis_requested", "indicator_updated", "candle_closed"})
_REGIME_INTERESTED_EVENT_TYPES = frozenset({"indicator_updated"})

# NOTE:
# These stream workers now use async Redis/consumer orchestration.
# Indicator, cross-market, pattern, regime, decision-context, signal-fusion and signal-history
# persistence now run through async services/repositories under a shared UoW.

if TYPE_CHECKING:
    from src.apps.patterns.task_services import PatternRealtimeService, PatternSignalContextService


async def _process_indicator_event(event: IrisEvent) -> IndicatorEventResult:
    async with AsyncUnitOfWork() as uow:
        result = await IndicatorAnalyticsService(uow).process_event(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            timestamp=event.timestamp,
        )
        if result.status == "ok":
            await uow.commit()
        return result


async def _capture_feature_snapshot_async(
    *,
    coin_id: int,
    timeframe: int,
    timestamp: datetime,
    price_current: float | None,
    rsi_14: float | None,
    macd: float | None,
) -> None:
    async with AsyncUnitOfWork() as uow:
        await FeatureSnapshotService(uow).capture_snapshot(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            price_current=price_current,
            rsi_14=rsi_14,
            macd=macd,
        )
        await uow.commit()


def _pattern_signal_context_service_factory(uow: BaseAsyncUnitOfWork) -> "PatternSignalContextService":
    from src.apps.patterns.task_services import PatternSignalContextService

    return PatternSignalContextService(uow)


def _pattern_realtime_service_factory(uow: BaseAsyncUnitOfWork) -> "PatternRealtimeService":
    from src.apps.patterns.task_services import PatternRealtimeService

    return PatternRealtimeService(uow)


async def _run_pattern_detection(event: IrisEvent) -> list[str]:
    async with AsyncUnitOfWork() as uow:
        result = await _pattern_realtime_service_factory(uow).detect_incremental_signals(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            candle_timestamp=event.timestamp,
            regime=str(event.payload.get("market_regime")) if event.payload.get("market_regime") is not None else None,
            lookback=200,
        )
        await uow.commit()
    return [str(item) for item in result.new_signal_types]


async def _run_regime_refresh(event: IrisEvent) -> PatternRegimeRefreshResult | None:
    async with AsyncUnitOfWork() as uow:
        result = await _pattern_realtime_service_factory(uow).refresh_regime_state(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            regime=str(event.payload.get("market_regime")) if event.payload.get("market_regime") is not None else None,
            regime_confidence=float(event.payload.get("regime_confidence") or 0.0),
        )
        if result is not None:
            await uow.commit()
        return result


def _emit_signal_created_events(
    *,
    coin_id: int,
    timeframe: int,
    timestamp: object,
    signal_types: Sequence[str],
) -> None:
    for signal_type in signal_types:
        publish_event(
            "signal_created",
            {
                "coin_id": coin_id,
                "timeframe": timeframe,
                "timestamp": timestamp,
                "signal_type": signal_type,
            },
        )


async def _handle_indicator_event(event: IrisEvent) -> None:
    result = await _process_indicator_event(event)
    if result.status != "ok":
        return
    for item in result.items:
        publish_event(
            "indicator_updated",
            {
                "coin_id": item.coin_id,
                "timeframe": item.timeframe,
                "timestamp": item.timestamp,
                "feature_source": item.feature_source,
                "activity_score": item.activity_score,
                "activity_bucket": item.activity_bucket,
                "analysis_priority": item.analysis_priority,
                "market_regime": item.market_regime,
                "regime_confidence": item.regime_confidence,
                "price_change_24h": item.price_change_24h,
                "price_change_7d": item.price_change_7d,
                "volatility": item.volatility,
            },
        )
        _emit_signal_created_events(
            coin_id=int(item.coin_id),
            timeframe=int(item.timeframe),
            timestamp=item.timestamp,
            signal_types=list(item.classic_signals),
        )


async def _handle_analysis_scheduler_event(event: IrisEvent) -> None:
    async with AsyncUnitOfWork() as uow:
        result = await AnalysisSchedulerService(uow).evaluate_indicator_update(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            timestamp=event.timestamp,
            activity_bucket_hint=(
                str(event.payload.get("activity_bucket")) if event.payload.get("activity_bucket") is not None else None
            ),
        )
        if not result.should_publish:
            return
        if result.state_updated:
            await uow.commit()
    publish_event(
        "analysis_requested",
        {
            "coin_id": event.coin_id,
            "timeframe": event.timeframe,
            "timestamp": event.timestamp,
            "activity_score": event.payload.get("activity_score"),
            "activity_bucket": result.activity_bucket,
            "analysis_priority": event.payload.get("analysis_priority"),
            "market_regime": event.payload.get("market_regime"),
            "regime_confidence": event.payload.get("regime_confidence"),
        },
    )


async def _handle_pattern_event(event: IrisEvent) -> None:
    if event.event_type not in _PATTERN_INTERESTED_EVENT_TYPES or event.coin_id <= 0 or event.timeframe <= 0:
        return
    new_signal_types = await _run_pattern_detection(event)
    if not new_signal_types:
        return
    for signal_type in new_signal_types:
        if signal_type.startswith("pattern_cluster_"):
            publish_event(
                "pattern_cluster_detected",
                {
                    "coin_id": event.coin_id,
                    "timeframe": event.timeframe,
                    "timestamp": event.timestamp,
                    "signal_type": signal_type,
                },
            )
        elif signal_type.startswith("pattern_"):
            publish_event(
                "pattern_detected",
                {
                    "coin_id": event.coin_id,
                    "timeframe": event.timeframe,
                    "timestamp": event.timestamp,
                    "signal_type": signal_type,
                },
            )
    _emit_signal_created_events(
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        timestamp=event.timestamp,
        signal_types=new_signal_types,
    )


async def _handle_regime_event(event: IrisEvent) -> None:
    if event.event_type not in _REGIME_INTERESTED_EVENT_TYPES or event.coin_id <= 0 or event.timeframe <= 0:
        return
    previous_regime = await read_cached_regime_async(coin_id=event.coin_id, timeframe=event.timeframe)
    cycle_result = await _run_regime_refresh(event)
    if cycle_result is None:
        return
    regime = cycle_result.regime
    regime_confidence = float(cycle_result.regime_confidence)
    if regime is not None:
        await cache_regime_snapshot_async(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            regime=regime,
            confidence=regime_confidence,
        )
    next_cycle = cycle_result.next_cycle
    previous_cycle = cycle_result.previous_cycle
    if regime != (previous_regime.regime if previous_regime is not None else None):
        publish_event(
            "market_regime_changed",
            {
                "coin_id": event.coin_id,
                "timeframe": event.timeframe,
                "timestamp": event.timestamp,
                "regime": regime,
                "confidence": regime_confidence,
            },
        )
    if next_cycle != previous_cycle:
        publish_event(
            "market_cycle_changed",
            {
                "coin_id": event.coin_id,
                "timeframe": event.timeframe,
                "timestamp": event.timestamp,
                "cycle_phase": next_cycle,
            },
        )


async def _handle_decision_event(event: IrisEvent) -> None:
    async with AsyncUnitOfWork() as uow:
        flow_result = await _pattern_signal_context_service_factory(uow).enrich(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            candle_timestamp=event.timestamp,
        )
    raw_decision = flow_result.get("decision", {})
    decision_result = dict(cast(Mapping[str, Any], raw_decision)) if isinstance(raw_decision, Mapping) else {}
    snapshot_payload = flow_result.get("_feature_snapshot")
    if isinstance(snapshot_payload, Mapping):
        await _capture_feature_snapshot_async(
            coin_id=int(snapshot_payload["coin_id"]),
            timeframe=int(snapshot_payload["timeframe"]),
            timestamp=cast(datetime, snapshot_payload["timestamp"]),
            price_current=cast(float | None, snapshot_payload.get("price_current")),
            rsi_14=cast(float | None, snapshot_payload.get("rsi_14")),
            macd=cast(float | None, snapshot_payload.get("macd")),
        )
    async with AsyncUnitOfWork() as uow:
        await SignalHistoryService(uow).refresh_recent_history(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
        )
        await uow.commit()
    if decision_result.get("status") == "ok":
        publish_event(
            "decision_generated",
            {
                "coin_id": event.coin_id,
                "timeframe": event.timeframe,
                "timestamp": event.timestamp,
                "decision": decision_result.get("decision"),
                "score": decision_result.get("score"),
            },
        )


async def _handle_fusion_event(event: IrisEvent) -> None:
    async with AsyncUnitOfWork() as uow:
        service = SignalFusionService(uow)
        result: SignalFusionResult | SignalFusionBatchResult
        if event.event_type == "news_symbol_correlation_updated":
            result = await service.evaluate_news_fusion_event(
                coin_id=event.coin_id,
                reference_timestamp=event.timestamp,
                emit_event=True,
            )
        else:
            result = await service.evaluate_market_decision(
                coin_id=event.coin_id,
                timeframe=event.timeframe,
                trigger_timestamp=None if event.event_type == "market_regime_changed" else event.timestamp,
                emit_event=True,
            )
        await uow.commit()
    await SignalFusionSideEffectDispatcher().apply(result)


async def _handle_cross_market_event(event: IrisEvent) -> None:
    if event.coin_id <= 0:
        return
    async with AsyncUnitOfWork() as uow:
        await CrossMarketService(uow).process_event(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            event_type=event.event_type,
            payload=event.payload,
            emit_events=True,
        )
        await uow.commit()


async def _handle_portfolio_event(event: IrisEvent) -> None:
    if event.event_type == "decision_generated" and event.payload.get("source") != "signal_fusion":
        return
    timeframe = int(event.timeframe)
    if timeframe <= 0:
        return
    async with AsyncUnitOfWork() as uow:
        result = await PortfolioService(uow).evaluate_portfolio_action(
            coin_id=event.coin_id,
            timeframe=timeframe,
            emit_events=True,
        )
        await uow.commit()
    await PortfolioSideEffectDispatcher().apply_action_result(result)


async def _handle_anomaly_event(event: IrisEvent) -> None:
    await _ANOMALY_CONSUMER.handle_event(event)


async def _handle_anomaly_sector_event(event: IrisEvent) -> None:
    await _ANOMALY_SECTOR_CONSUMER.handle_event(event)


async def _handle_news_normalization_event(event: IrisEvent) -> None:
    await _NEWS_NORMALIZATION_CONSUMER.handle_event(event)


async def _handle_news_correlation_event(event: IrisEvent) -> None:
    await _NEWS_CORRELATION_CONSUMER.handle_event(event)


async def _handle_hypothesis_event(event: IrisEvent) -> None:
    await _HYPOTHESIS_CONSUMER.handle_event(event)


async def _handle_notification_event(event: IrisEvent) -> None:
    await _NOTIFICATION_CONSUMER.handle_event(event)


def create_worker(group_name: str, consumer_name: str | None = None) -> EventConsumer:
    settings = get_settings()
    effective_consumer_name = consumer_name or default_consumer_name(group_name)
    config = EventConsumerConfig(
        group_name=group_name,
        consumer_name=effective_consumer_name,
        stream_name=build_delivery_stream_name(group_name),
        batch_size=settings.event_worker_batch_size,
        block_milliseconds=settings.event_worker_block_milliseconds,
        pending_idle_milliseconds=settings.event_worker_pending_idle_milliseconds,
    )
    if group_name == INDICATOR_WORKER_GROUP:
        return EventConsumer(
            config, handler=_handle_indicator_event, interested_event_types=None, metrics_store=_CONTROL_PLANE_METRICS
        )
    if group_name == ANALYSIS_SCHEDULER_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_analysis_scheduler_event,
            interested_event_types=None,
            metrics_store=_CONTROL_PLANE_METRICS,
        )
    if group_name == PATTERN_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_pattern_event,
            interested_event_types=set(_PATTERN_INTERESTED_EVENT_TYPES),
            metrics_store=_CONTROL_PLANE_METRICS,
        )
    if group_name == REGIME_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_regime_event,
            interested_event_types=set(_REGIME_INTERESTED_EVENT_TYPES),
            metrics_store=_CONTROL_PLANE_METRICS,
        )
    if group_name == DECISION_WORKER_GROUP:
        return EventConsumer(
            config, handler=_handle_decision_event, interested_event_types=None, metrics_store=_CONTROL_PLANE_METRICS
        )
    if group_name == FUSION_WORKER_GROUP:
        return EventConsumer(
            config, handler=_handle_fusion_event, interested_event_types=None, metrics_store=_CONTROL_PLANE_METRICS
        )
    if group_name == CROSS_MARKET_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_cross_market_event,
            interested_event_types=None,
            metrics_store=_CONTROL_PLANE_METRICS,
        )
    if group_name == PORTFOLIO_WORKER_GROUP:
        return EventConsumer(
            config, handler=_handle_portfolio_event, interested_event_types=None, metrics_store=_CONTROL_PLANE_METRICS
        )
    if group_name == ANOMALY_WORKER_GROUP:
        return EventConsumer(
            config, handler=_handle_anomaly_event, interested_event_types=None, metrics_store=_CONTROL_PLANE_METRICS
        )
    if group_name == ANOMALY_SECTOR_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_anomaly_sector_event,
            interested_event_types=None,
            metrics_store=_CONTROL_PLANE_METRICS,
        )
    if group_name == NEWS_NORMALIZATION_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_news_normalization_event,
            interested_event_types=None,
            metrics_store=_CONTROL_PLANE_METRICS,
        )
    if group_name == NEWS_CORRELATION_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_news_correlation_event,
            interested_event_types=None,
            metrics_store=_CONTROL_PLANE_METRICS,
        )
    if group_name == HYPOTHESIS_WORKER_GROUP:
        return EventConsumer(
            config, handler=_handle_hypothesis_event, interested_event_types=None, metrics_store=_CONTROL_PLANE_METRICS
        )
    if group_name == NOTIFICATION_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_notification_event,
            interested_event_types=None,
            metrics_store=_CONTROL_PLANE_METRICS,
        )
    raise ValueError(f"Unsupported event worker group '{group_name}'.")
