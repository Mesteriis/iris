from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.events.consumer import EventConsumer, EventConsumerConfig, default_consumer_name
from app.events.publisher import publish_event
from app.events.types import (
    DECISION_WORKER_GROUP,
    INDICATOR_WORKER_GROUP,
    IrisEvent,
    PATTERN_WORKER_GROUP,
    REGIME_WORKER_GROUP,
)
from app.models.coin import Coin
from app.models.market_cycle import MarketCycle
from app.models.signal import Signal
from app.patterns.clusters import build_pattern_clusters
from app.patterns.context import enrich_signal_context
from app.patterns.cycle import update_market_cycle
from app.patterns.decision import evaluate_investment_decision
from app.patterns.engine import PatternEngine
from app.patterns.hierarchy import build_hierarchy_signals
from app.patterns.narrative import refresh_sector_metrics
from app.patterns.risk import evaluate_final_signal
from app.services.analytics_service import (
    determine_affected_timeframes,
    process_indicator_event,
)
from app.services.feature_snapshots_service import capture_feature_snapshot
from app.services.signal_history_service import refresh_recent_signal_history

LOGGER = logging.getLogger(__name__)
EVENT_WORKER_GROUPS = (
    INDICATOR_WORKER_GROUP,
    PATTERN_WORKER_GROUP,
    REGIME_WORKER_GROUP,
    DECISION_WORKER_GROUP,
)
_PATTERN_ENGINE = PatternEngine()


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


def _handle_indicator_event(event: IrisEvent) -> None:
    db = SessionLocal()
    try:
        result = process_indicator_event(
            db,
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            timestamp=event.timestamp,
        )
        if result.get("status") != "ok":
            return
        for item in result.get("items", []):
            publish_event(
                "indicator_updated",
                {
                    "coin_id": item["coin_id"],
                    "timeframe": item["timeframe"],
                    "timestamp": item["timestamp"],
                    "feature_source": item.get("feature_source"),
                },
            )
            _emit_signal_created_events(
                coin_id=int(item["coin_id"]),
                timeframe=int(item["timeframe"]),
                timestamp=item["timestamp"],
                signal_types=list(item.get("classic_signals", [])),
            )
    finally:
        db.close()


def _handle_pattern_event(event: IrisEvent) -> None:
    db = SessionLocal()
    try:
        existing_signal_types = _signal_types_at_timestamp(
            db,
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            timestamp=event.timestamp,
        )
        _PATTERN_ENGINE.detect_incremental(db, coin_id=event.coin_id, timeframe=event.timeframe, lookback=200)
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
        new_signal_types = sorted(current_signal_types - existing_signal_types)
        if not new_signal_types:
            return
        _emit_signal_created_events(
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            timestamp=event.timestamp,
            signal_types=new_signal_types,
        )
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
    finally:
        db.close()


def _regime_state_key(event: IrisEvent) -> str:
    return f"{event.coin_id}:{event.timeframe}"


_LAST_REGIME_STATE: dict[str, tuple[str | None, str | None]] = {}


def _handle_regime_event(event: IrisEvent) -> None:
    db = SessionLocal()
    try:
        coin = db.get(Coin, event.coin_id)
        if coin is None:
            return
        refresh_sector_metrics(db, timeframe=event.timeframe)
        cycle_before = db.get(MarketCycle, (event.coin_id, event.timeframe))
        cycle_before_phase = cycle_before.cycle_phase if cycle_before is not None else None
        cycle_result = update_market_cycle(
            db,
            coin_id=event.coin_id,
            timeframe=event.timeframe,
        )
        regime = None
        metrics = coin.metrics
        if metrics is not None and metrics.market_regime_details:
            detailed = metrics.market_regime_details.get(str(event.timeframe))
            regime = detailed.get("regime") if isinstance(detailed, dict) else metrics.market_regime
        elif metrics is not None:
            regime = metrics.market_regime
        state_key = _regime_state_key(event)
        previous_regime, previous_cycle = _LAST_REGIME_STATE.get(state_key, (None, cycle_before_phase))
        next_cycle = cycle_result.get("cycle_phase")
        if regime != previous_regime:
            publish_event(
                "market_regime_changed",
                {
                    "coin_id": event.coin_id,
                    "timeframe": event.timeframe,
                    "timestamp": event.timestamp,
                    "regime": regime,
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
        _LAST_REGIME_STATE[state_key] = (regime, str(next_cycle) if next_cycle is not None else None)
    finally:
        db.close()


def _latest_indicator_value(db, *, coin_id: int, timeframe: int, indicator: str, timestamp: object) -> float | None:
    from app.models.indicator_cache import IndicatorCache

    value = db.scalar(
        select(IndicatorCache.value).where(
            IndicatorCache.coin_id == coin_id,
            IndicatorCache.timeframe == timeframe,
            IndicatorCache.indicator == indicator,
            IndicatorCache.timestamp == timestamp,
        )
    )
    return float(value) if value is not None else None


def _handle_decision_event(event: IrisEvent) -> None:
    db = SessionLocal()
    try:
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
        capture_feature_snapshot(
            db,
            coin_id=event.coin_id,
            timeframe=event.timeframe,
            timestamp=event.timestamp,
            price_current=_latest_indicator_value(
                db,
                coin_id=event.coin_id,
                timeframe=event.timeframe,
                indicator="price_current",
                timestamp=event.timestamp,
            ),
            rsi_14=_latest_indicator_value(
                db,
                coin_id=event.coin_id,
                timeframe=event.timeframe,
                indicator="rsi_14",
                timestamp=event.timestamp,
            ),
            macd=_latest_indicator_value(
                db,
                coin_id=event.coin_id,
                timeframe=event.timeframe,
                indicator="macd",
                timestamp=event.timestamp,
            ),
            commit=True,
        )
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
    finally:
        db.close()


def create_worker(group_name: str, consumer_name: str | None = None) -> EventConsumer:
    settings = get_settings()
    effective_consumer_name = consumer_name or default_consumer_name(group_name)
    config = EventConsumerConfig(
        group_name=group_name,
        consumer_name=effective_consumer_name,
        stream_name=settings.event_stream_name,
        batch_size=settings.event_worker_batch_size,
        block_milliseconds=settings.event_worker_block_milliseconds,
        pending_idle_milliseconds=settings.event_worker_pending_idle_milliseconds,
    )
    if group_name == INDICATOR_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_indicator_event,
            interested_event_types={"candle_closed"},
        )
    if group_name == PATTERN_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_pattern_event,
            interested_event_types={"indicator_updated"},
        )
    if group_name == REGIME_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_regime_event,
            interested_event_types={"indicator_updated"},
        )
    if group_name == DECISION_WORKER_GROUP:
        return EventConsumer(
            config,
            handler=_handle_decision_event,
            interested_event_types={
                "pattern_detected",
                "pattern_cluster_detected",
                "market_regime_changed",
                "market_cycle_changed",
                "signal_created",
            },
        )
    raise ValueError(f"Unsupported event worker group '{group_name}'.")
