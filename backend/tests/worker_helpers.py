import os
import time
from typing import Any

from iris.core.settings import get_settings
from iris.runtime.streams.consumer import EventConsumer, EventConsumerConfig
from iris.runtime.streams.types import IrisEvent
from redis import Redis


def recording_worker_loop(
    *,
    stream_name: str,
    group_name: str,
    consumer_name: str,
    record_hash: str,
    interested_event_types: set[str],
    pending_idle_milliseconds: int = 200,
) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    def handler(event: IrisEvent) -> None:
        time.sleep(0.05)
        redis.hincrby(record_hash, consumer_name, 1)
        redis.hset(record_hash, f"last:{consumer_name}", event.stream_id)

    consumer = EventConsumer(
        EventConsumerConfig(
            group_name=group_name,
            consumer_name=consumer_name,
            stream_name=stream_name,
            batch_size=1,
            block_milliseconds=100,
            pending_idle_milliseconds=pending_idle_milliseconds,
        ),
        handler=handler,
        interested_event_types=interested_event_types,
    )
    try:
        consumer.run()
    finally:
        consumer.close()
        redis.close()


def crashing_worker_loop(
    *,
    stream_name: str,
    group_name: str,
    consumer_name: str,
    interested_event_types: set[str],
) -> None:
    settings = get_settings()

    def handler(event: IrisEvent) -> None:
        del event
        os._exit(1)

    consumer = EventConsumer(
        EventConsumerConfig(
            group_name=group_name,
            consumer_name=consumer_name,
            stream_name=stream_name,
            batch_size=1,
            block_milliseconds=100,
            pending_idle_milliseconds=100,
        ),
        handler=handler,
        interested_event_types=interested_event_types,
    )
    consumer.run()
