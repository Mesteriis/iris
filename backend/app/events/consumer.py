from __future__ import annotations

import logging
import os
import socket
import time
from dataclasses import dataclass
from typing import Callable

from redis import Redis
from redis.exceptions import RedisError, ResponseError

from app.core.config import get_settings
from app.events.types import EVENT_STREAM_NAME, IrisEvent, parse_stream_message

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EventConsumerConfig:
    group_name: str
    consumer_name: str
    stream_name: str = EVENT_STREAM_NAME
    batch_size: int = 10
    block_milliseconds: int = 1000
    pending_idle_milliseconds: int = 30_000
    processed_ttl_seconds: int = 604_800


class EventConsumer:
    def __init__(
        self,
        config: EventConsumerConfig,
        *,
        handler: Callable[[IrisEvent], None],
        interested_event_types: set[str] | None = None,
        redis_url: str | None = None,
    ) -> None:
        settings = get_settings()
        self._config = config
        self._handler = handler
        self._interested_event_types = interested_event_types
        self._redis = Redis.from_url(redis_url or settings.redis_url, decode_responses=True)
        self._stop_requested = False

    def _processed_key(self, event: IrisEvent) -> str:
        return f"iris:events:processed:{self._config.group_name}:{event.idempotency_key}"

    def _ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                name=self._config.stream_name,
                groupname=self._config.group_name,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def stop(self) -> None:
        self._stop_requested = True

    def _mark_processed(self, event: IrisEvent) -> None:
        self._redis.set(
            self._processed_key(event),
            event.stream_id,
            ex=self._config.processed_ttl_seconds,
        )

    def _already_processed(self, event: IrisEvent) -> bool:
        return self._redis.exists(self._processed_key(event)) == 1

    def _iter_stale_messages(self) -> list[tuple[str, dict[str, str]]]:
        try:
            message_id, entries, _ = self._redis.xautoclaim(
                name=self._config.stream_name,
                groupname=self._config.group_name,
                consumername=self._config.consumer_name,
                min_idle_time=self._config.pending_idle_milliseconds,
                start_id="0-0",
                count=self._config.batch_size,
            )
        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                self._ensure_group()
                return []
            raise
        except RedisError:
            return []
        del message_id
        return [(entry_id, fields) for entry_id, fields in entries]

    def _iter_new_messages(self) -> list[tuple[str, dict[str, str]]]:
        try:
            entries = self._redis.xreadgroup(
                groupname=self._config.group_name,
                consumername=self._config.consumer_name,
                streams={self._config.stream_name: ">"},
                count=self._config.batch_size,
                block=self._config.block_milliseconds,
            )
        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                self._ensure_group()
                return []
            raise
        if not entries:
            return []
        return [
            (message_id, fields)
            for _, messages in entries
            for message_id, fields in messages
        ]

    def _process_message(self, message_id: str, fields: dict[str, str]) -> None:
        event = parse_stream_message(message_id, fields)
        if self._already_processed(event):
            self._redis.xack(self._config.stream_name, self._config.group_name, message_id)
            return
        if self._interested_event_types is not None and event.event_type not in self._interested_event_types:
            self._mark_processed(event)
            self._redis.xack(self._config.stream_name, self._config.group_name, message_id)
            return
        self._handler(event)
        self._mark_processed(event)
        self._redis.xack(self._config.stream_name, self._config.group_name, message_id)

    def run(self, *, stop_checker: Callable[[], bool] | None = None) -> None:
        self._ensure_group()
        while not self._stop_requested and not (stop_checker() if stop_checker is not None else False):
            try:
                messages = self._iter_stale_messages()
                if not messages:
                    messages = self._iter_new_messages()
                if not messages:
                    continue
                for message_id, fields in messages:
                    self._process_message(message_id, fields)
            except RedisError as exc:  # pragma: no cover
                LOGGER.warning(
                    "Event consumer group=%s consumer=%s error=%s",
                    self._config.group_name,
                    self._config.consumer_name,
                    exc,
                )
                time.sleep(1.0)
            except Exception as exc:  # pragma: no cover
                LOGGER.exception(
                    "Event consumer group=%s consumer=%s handler failed: %s",
                    self._config.group_name,
                    self._config.consumer_name,
                    exc,
                )
                time.sleep(0.5)

    def close(self) -> None:
        self._redis.close()


def default_consumer_name(group_name: str) -> str:
    return f"{group_name}-{socket.gethostname()}-{os.getpid()}"
