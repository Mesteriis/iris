from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select

from src.apps.anomalies.consumers import CandleAnomalyConsumer, SectorAnomalyConsumer
from src.apps.control_plane.metrics import ControlPlaneMetricsStore
from src.apps.cross_market.services import CrossMarketService
from src.apps.hypothesis_engine.consumers import HypothesisConsumer
from src.apps.indicators.models import CoinMetrics
from src.apps.indicators.services import FeatureSnapshotService, IndicatorAnalyticsService
from src.apps.market_data.models import Coin
from src.apps.news.consumers import NewsCorrelationConsumer, NewsNormalizationConsumer
from src.apps.patterns.cache import cache_regime_snapshot_async, read_cached_regime_async
from src.apps.patterns.domain.clusters import build_pattern_clusters
from src.apps.patterns.domain.context import enrich_signal_context
from src.apps.patterns.domain.cycle import update_market_cycle
from src.apps.patterns.domain.decision import evaluate_investment_decision
from src.apps.patterns.domain.engine import PatternEngine
from src.apps.patterns.domain.hierarchy import build_hierarchy_signals
from src.apps.patterns.domain.narrative import refresh_sector_metrics
from src.apps.patterns.domain.risk import evaluate_final_signal
from src.apps.patterns.domain.scheduler import should_request_analysis
from src.apps.patterns.models import MarketCycle
from src.apps.portfolio.engine import evaluate_portfolio_action
from src.apps.signals.history import refresh_recent_signal_history
from src.apps.signals.models import Signal
from src.apps.signals.services import SignalFusionService, SignalFusionSideEffectDispatcher
from src.core.db.session import AsyncSessionLocal
from src.core.db.uow import AsyncUnitOfWork
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
    EVENT_WORKER_GROUPS,
    FUSION_WORKER_GROUP,
    HYPOTHESIS_WORKER_GROUP,
    INDICATOR_WORKER_GROUP,
    NEWS_CORRELATION_WORKER_GROUP,
    NEWS_NORMALIZATION_WORKER_GROUP,
    PATTERN_WORKER_GROUP,
    PORTFOLIO_WORKER_GROUP,
    REGIME_WORKER_GROUP,
    IrisEvent,
)

LOGGER = logging.getLogger(__name__)
_PATTERN_ENGINE = PatternEngine()
_ANOMALY_CONSUMER = CandleAnomalyConsumer()
_ANOMALY_SECTOR_CONSUMER = SectorAnomalyConsumer()
_NEWS_NORMALIZATION_CONSUMER = NewsNormalizationConsumer()
_NEWS_CORRELATION_CONSUMER = NewsCorrelationConsumer()
_HYPOTHESIS_CONSUMER = HypothesisConsumer()
_CONTROL_PLANE_METRICS = ControlPlaneMetricsStore()

# NOTE:
# These stream workers now use async Redis/consumer orchestration.
# Indicator, cross-market and signal-fusion persistence now run through async repositories/UoW.
# Remaining decision/history orchestration still relies on legacy sync cores behind AsyncSession.run_sync.


async def _run_worker_db(fn):
    async with AsyncSessionLocal() as db:
        return await db.run_sync(fn)


async def _process_indicator_event(event: IrisEvent):
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
    timestamp: object,
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


def _signal_types_at_timestamp(db, *, coin_id: int, timeframe: int, timestamp: object) -> set[str]:
    return set(
        db.scalars(
            select(Signal.signal_type).where(
                Signal.coin_id == coin_id,
                Signal.timeframe == timeframe,
                Signal.candle_timestamp == timestamp,
            )
        ).all()
    )


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
    async with AsyncSessionLocal() as db:
        metrics = await db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == event.coin_id))
        activity_bucket = (
            str(event.payload.get("activity_bucket"))
            if event.payload.get("activity_bucket") is not None
            else (metrics.activity_bucket if metrics is not None else None)
        )
        last_analysis_at = metrics.last_analysis_at if metrics is not None else None
        if not should_request_analysis(
            timeframe=event.timeframe,
            timestamp=event.timestamp,
            activity_bucket=activity_bucket,
            last_analysis_at=last_analysis_at,
        ):
            return
        if metrics is not None:
            metrics.last_analysis_at = event.timestamp
            await db.commit()
    publish_event(
        "analysis_requested",
        {
            "coin_id": event.coin_id,
            "timeframe": event.timeframe,
            "timestamp": event.timestamp,
            "activity_score": event.payload.get("activity_score"),
            "activity_bucket": activity_bucket,
            "analysis_priority": event.payload.get("analysis_priority"),
            "market_regime": event.payload.get("market_regime"),
            "regime_confidence": event.payload.get("regime_confidence"),
        },
    )


async def _handle_pattern_event(event: IrisEvent) -> None:
    new_signal_types = await _run_worker_db(lambda db: _detect_pattern_signals(db, event))
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
    previous_regime = await read_cached_regime_async(coin_id=event.coin_id, timeframe=event.timeframe)
    cycle_result = await _run_worker_db(lambda db: _refresh_regime_state(db, event))
    if cycle_result is None:
        return
    regime = cycle_result["regime"]
    regime_confidence = float(cycle_result["regime_confidence"])
    if regime is not None:
        await cache_regime_snapshot_async(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            regime=regime,
            confidence=regime_confidence,
        )
    next_cycle = cycle_result["next_cycle"]
    previous_cycle = cycle_result["previous_cycle"]
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


def _latest_indicator_value(db, *, coin_id: int, timeframe: int, indicator: str, timestamp: object) -> float | None:
    from src.apps.indicators.models import IndicatorCache

    value = db.scalar(
        select(IndicatorCache.value).where(
            IndicatorCache.coin_id == coin_id,
            IndicatorCache.timeframe == timeframe,
            IndicatorCache.indicator == indicator,
            IndicatorCache.timestamp == timestamp,
        )
    )
    return float(value) if value is not None else None


async def _handle_decision_event(event: IrisEvent) -> None:
    decision_result = await _run_worker_db(lambda db: _evaluate_decision_flow(db, event))
    snapshot_payload = decision_result.pop("_feature_snapshot", None)
    if snapshot_payload is not None:
        await _capture_feature_snapshot_async(**snapshot_payload)
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


async def _handle_portfolio_event(event: IrisEvent) -> None:
    if event.event_type == "decision_generated" and event.payload.get("source") != "signal_fusion":
        return
    timeframe = int(event.timeframe)
    if timeframe <= 0:
        return
    await _run_worker_db(
        lambda db: evaluate_portfolio_action(
            db,
            coin_id=event.coin_id,
            timeframe=timeframe,
            emit_events=True,
        )
    )


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


def _detect_pattern_signals(db, event: IrisEvent) -> list[str]:
    existing_signal_types = _signal_types_at_timestamp(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        timestamp=event.timestamp,
    )
    _PATTERN_ENGINE.detect_incremental(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        lookback=200,
        regime=str(event.payload.get("market_regime")) if event.payload.get("market_regime") is not None else None,
    )
    build_pattern_clusters(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        candle_timestamp=event.timestamp,
    )
    build_hierarchy_signals(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        candle_timestamp=event.timestamp,
    )
    current_signal_types = _signal_types_at_timestamp(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        timestamp=event.timestamp,
    )
    return sorted(current_signal_types - existing_signal_types)


def _refresh_regime_state(db, event: IrisEvent) -> dict[str, object] | None:
    coin = db.get(Coin, event.coin_id)
    if coin is None:
        return None
    refresh_sector_metrics(db, timeframe=event.timeframe)
    cycle_before = db.get(MarketCycle, (event.coin_id, event.timeframe))
    cycle_result = update_market_cycle(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
    )
    return {
        "previous_cycle": cycle_before.cycle_phase if cycle_before is not None else None,
        "next_cycle": cycle_result.get("cycle_phase"),
        "regime": (str(event.payload.get("market_regime")) if event.payload.get("market_regime") is not None else None),
        "regime_confidence": float(event.payload.get("regime_confidence") or 0.0),
    }


def _evaluate_decision_flow(db, event: IrisEvent) -> dict[str, object]:
    enrich_signal_context(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        candle_timestamp=event.timestamp,
        commit=True,
    )
    decision_result = evaluate_investment_decision(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        emit_event=True,
    )
    evaluate_final_signal(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        emit_event=True,
    )
    refresh_recent_signal_history(
        db,
        coin_id=event.coin_id,
        timeframe=event.timeframe,
        commit=True,
    )
    return {
        **decision_result,
        "_feature_snapshot": {
            "coin_id": event.coin_id,
            "timeframe": event.timeframe,
            "timestamp": event.timestamp,
            "price_current": _latest_indicator_value(
                db,
                coin_id=event.coin_id,
                timeframe=event.timeframe,
                indicator="price_current",
                timestamp=event.timestamp,
            ),
            "rsi_14": _latest_indicator_value(
                db,
                coin_id=event.coin_id,
                timeframe=event.timeframe,
                indicator="rsi_14",
                timestamp=event.timestamp,
            ),
            "macd": _latest_indicator_value(
                db,
                coin_id=event.coin_id,
                timeframe=event.timeframe,
                indicator="macd",
                timestamp=event.timestamp,
            ),
        },
    }


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
            config, handler=_handle_pattern_event, interested_event_types=None, metrics_store=_CONTROL_PLANE_METRICS
        )
    if group_name == REGIME_WORKER_GROUP:
        return EventConsumer(
            config, handler=_handle_regime_event, interested_event_types=None, metrics_store=_CONTROL_PLANE_METRICS
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
    raise ValueError(f"Unsupported event worker group '{group_name}'.")
