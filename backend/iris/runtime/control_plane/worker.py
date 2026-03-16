from typing import Any

from redis.asyncio import Redis as AsyncRedis

from iris.apps.control_plane.cache import TopologyCacheManager
from iris.apps.control_plane.contracts import EventConsumerSnapshot, EventRouteSnapshot
from iris.apps.control_plane.control_events import CONTROL_EVENT_TYPES
from iris.apps.control_plane.metrics import ControlPlaneMetricsStore
from iris.core.settings import get_settings
from iris.runtime.control_plane.dispatcher import InMemoryDispatchTracker, TopologyDispatcher, TopologyRouteEvaluator
from iris.runtime.streams.consumer import EventConsumer, EventConsumerConfig, default_consumer_name
from iris.runtime.streams.types import IrisEvent, build_event_fields

TOPOLOGY_DISPATCHER_GROUP = "control_plane_dispatcher"


def build_delivery_stream_name(consumer_key: str) -> str:
    return f"iris:deliveries:{consumer_key}"


class RedisRouteDeliveryPublisher:
    def __init__(self, redis_url: str | None = None) -> None:
        settings = get_settings()
        self._redis = AsyncRedis.from_url(redis_url or settings.redis_url, decode_responses=True)

    async def publish(
        self,
        *,
        route: EventRouteSnapshot,
        consumer: EventConsumerSnapshot,
        event: IrisEvent,
        shadow: bool,
    ) -> None:
        metadata = {
            **event.metadata,
            "route_key": route.route_key,
            "consumer_key": consumer.consumer_key,
            "shadow": shadow,
            "source_producer": event.producer,
        }
        payload: dict[str, Any] = {
            **dict(event.payload),
            "coin_id": int(event.coin_id),
            "timeframe": int(event.timeframe),
            "timestamp": event.timestamp,
            "event_id": event.event_id,
            "causation_id": event.event_id,
            "correlation_id": event.correlation_id,
            "parent_event_id": event.parent_event_id or event.event_id,
            "producer": "control_plane.dispatcher",
            "occurred_at": event.occurred_at.isoformat(),
            "metadata": metadata,
        }
        if event.symbol is not None:
            payload["symbol"] = event.symbol
        if event.exchange is not None:
            payload["exchange"] = event.exchange
        if event.confidence is not None:
            payload["confidence"] = float(event.confidence)
        fields = build_event_fields(event.event_type, payload)
        await self._redis.xadd(consumer.delivery_stream, fields=fields)

    async def close(self) -> None:
        await self._redis.aclose()


class TopologyDispatchService:
    def __init__(
        self,
        *,
        cache_manager: TopologyCacheManager | None = None,
        publisher: RedisRouteDeliveryPublisher | None = None,
        metrics_store: ControlPlaneMetricsStore | None = None,
        environment: str | None = None,
    ) -> None:
        settings = get_settings()
        self._cache_manager = cache_manager or TopologyCacheManager()
        self._publisher = publisher or RedisRouteDeliveryPublisher()
        self._metrics = metrics_store or ControlPlaneMetricsStore()
        self._environment = environment or settings.app_env
        self._evaluator = TopologyRouteEvaluator(environment=self._environment)
        self._tracker = InMemoryDispatchTracker()

    async def handle_event(self, event: IrisEvent) -> dict[str, object]:
        if event.event_type in CONTROL_EVENT_TYPES:
            await self._cache_manager.refresh_from_control_event(event)
        snapshot = await self._cache_manager.get_snapshot()
        dispatcher = TopologyDispatcher(
            snapshot=snapshot,
            publisher=self._publisher,
            evaluator=self._evaluator,
            tracker=self._tracker,
        )
        report = await dispatcher.dispatch(event)
        for decision in report.decisions:
            await self._metrics.record_route_dispatch(
                route_key=decision.route.route_key,
                consumer_key=decision.consumer.consumer_key,
                delivered=decision.deliver,
                shadow=decision.shadow,
                reason=decision.reason,
                occurred_at=event.occurred_at,
            )
        return {
            "event_id": report.event_id,
            "event_type": report.event_type,
            "version_number": report.version_number,
            "delivered": report.delivered_count,
            "shadow": report.shadow_count,
            "skipped": report.skipped_count,
        }

    async def close(self) -> None:
        await self._publisher.close()


def create_topology_dispatcher_consumer(consumer_name: str | None = None) -> EventConsumer:
    settings = get_settings()
    config = EventConsumerConfig(
        group_name=TOPOLOGY_DISPATCHER_GROUP,
        consumer_name=consumer_name or default_consumer_name(TOPOLOGY_DISPATCHER_GROUP),
        stream_name=settings.event_stream_name,
        batch_size=settings.event_worker_batch_size,
        block_milliseconds=settings.event_worker_block_milliseconds,
        pending_idle_milliseconds=settings.event_worker_pending_idle_milliseconds,
    )
    service = TopologyDispatchService(environment=settings.app_env)
    return EventConsumer(config, handler=service.handle_event, interested_event_types=None)


__all__ = [
    "TOPOLOGY_DISPATCHER_GROUP",
    "RedisRouteDeliveryPublisher",
    "TopologyDispatchService",
    "build_delivery_stream_name",
    "create_topology_dispatcher_consumer",
]
