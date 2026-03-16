from collections.abc import Awaitable, Callable

from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ResponseError

from iris.core.settings import get_settings
from iris.runtime.streams.consumer import EventConsumer, EventConsumerConfig, default_consumer_name
from iris.runtime.streams.types import IrisEvent

HA_BRIDGE_GROUP = "ha_bridge"
HA_SUPPORTED_EVENT_TYPES = frozenset(
    {
        "indicator_updated",
        "decision_generated",
        "market_regime_changed",
        "pattern_boosted",
        "pattern_degraded",
        "pattern_disabled",
        "prediction_confirmed",
        "prediction_failed",
        "portfolio_balance_updated",
        "portfolio_position_changed",
        "portfolio_position_opened",
        "portfolio_position_closed",
        "portfolio_rebalanced",
    }
)


async def ensure_ha_bridge_group() -> None:
    settings = get_settings()
    client = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.xgroup_create(
            name=settings.event_stream_name,
            groupname=HA_BRIDGE_GROUP,
            id="$",
            mkstream=True,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    finally:
        await client.aclose()


def create_ha_bridge_consumer(
    *,
    handler: Callable[[IrisEvent], Awaitable[object]],
    consumer_name: str | None = None,
) -> EventConsumer:
    settings = get_settings()
    config = EventConsumerConfig(
        group_name=HA_BRIDGE_GROUP,
        consumer_name=consumer_name or default_consumer_name(HA_BRIDGE_GROUP),
        stream_name=settings.event_stream_name,
        batch_size=settings.event_worker_batch_size,
        block_milliseconds=settings.event_worker_block_milliseconds,
        pending_idle_milliseconds=settings.event_worker_pending_idle_milliseconds,
    )
    return EventConsumer(
        config=config,
        handler=handler,
        interested_event_types=set(HA_SUPPORTED_EVENT_TYPES),
    )


__all__ = ["HA_BRIDGE_GROUP", "HA_SUPPORTED_EVENT_TYPES", "create_ha_bridge_consumer", "ensure_ha_bridge_group"]
