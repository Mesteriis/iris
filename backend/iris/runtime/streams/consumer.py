import asyncio
import inspect
import logging
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError

from iris.core.settings import get_settings
from iris.runtime.streams.types import EVENT_STREAM_NAME, IrisEvent, parse_stream_message

LOGGER = logging.getLogger(__name__)


# NOTE:
# Event consumers run on dedicated worker processes and now use async Redis I/O.
# The remaining sync pieces live deeper in specific worker handlers where legacy
# domain logic is still being migrated.
@dataclass(frozen=True, slots=True)
class EventConsumerConfig:
    group_name: str
    consumer_name: str
    stream_name: str = EVENT_STREAM_NAME
    batch_size: int = 10
    block_milliseconds: int = 1000
    pending_idle_milliseconds: int = 30_000
    processed_ttl_seconds: int = 604_800


class ConsumerMetricsRecorder(Protocol):
    async def record_consumer_result(
        self,
        *,
        consumer_key: str,
        route_key: str | None,
        occurred_at: datetime,
        succeeded: bool,
        error: str | None = None,
    ) -> None: ...


class EventConsumer:
    def __init__(
        self,
        config: EventConsumerConfig,
        *,
        handler: Callable[[IrisEvent], object],
        interested_event_types: set[str] | None = None,
        redis_url: str | None = None,
        metrics_store: ConsumerMetricsRecorder | None = None,
        metrics_consumer_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self._config = config
        self._handler = handler
        self._interested_event_types = interested_event_types
        self._redis = Redis.from_url(redis_url or settings.redis_url, decode_responses=True)
        self._metrics_store = metrics_store
        self._metrics_consumer_key = metrics_consumer_key or config.group_name
        self._stop_requested = False

    def _processed_key(self, event: IrisEvent) -> str:
        return f"iris:events:processed:{self._config.group_name}:{event.idempotency_key}"

    async def _ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(
                name=self._config.stream_name,
                groupname=self._config.group_name,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    def _is_missing_group_error(exc: ResponseError) -> bool:
        return "NOGROUP" in str(exc)

    @staticmethod
    def _is_missing_stream_unblocked_error(exc: ResponseError) -> bool:
        normalized = str(exc).upper()
        return "UNBLOCKED" in normalized and "STREAM KEY NO LONGER EXISTS" in normalized

    def stop(self) -> None:
        self._stop_requested = True

    async def _mark_processed(self, event: IrisEvent) -> None:
        await self._redis.set(
            self._processed_key(event),
            event.stream_id,
            ex=self._config.processed_ttl_seconds,
        )

    async def _already_processed(self, event: IrisEvent) -> bool:
        return bool(await self._redis.exists(self._processed_key(event)))

    async def _iter_stale_messages(self) -> list[tuple[str, dict[str, str]]]:
        try:
            message_id, entries, _ = await self._redis.xautoclaim(
                name=self._config.stream_name,
                groupname=self._config.group_name,
                consumername=self._config.consumer_name,
                min_idle_time=self._config.pending_idle_milliseconds,
                start_id="0-0",
                count=self._config.batch_size,
            )
        except ResponseError as exc:
            if self._is_missing_group_error(exc) or self._is_missing_stream_unblocked_error(exc):
                await self._ensure_group()
                return []
            raise
        except RedisError:
            return []
        del message_id
        return list(entries)

    async def _iter_new_messages(self) -> list[tuple[str, dict[str, str]]]:
        try:
            entries = await self._redis.xreadgroup(
                groupname=self._config.group_name,
                consumername=self._config.consumer_name,
                streams={self._config.stream_name: ">"},
                count=self._config.batch_size,
                block=self._config.block_milliseconds,
            )
        except ResponseError as exc:
            if self._is_missing_group_error(exc) or self._is_missing_stream_unblocked_error(exc):
                await self._ensure_group()
                return []
            raise
        if not entries:
            return []
        return [
            (message_id, fields)
            for _, messages in entries
            for message_id, fields in messages
        ]

    async def _invoke_handler(self, event: IrisEvent) -> None:
        result = self._handler(event)
        if inspect.isawaitable(result):
            await result

    async def _process_message(self, message_id: str, fields: dict[str, str]) -> None:
        event = parse_stream_message(message_id, fields)
        if await self._already_processed(event):
            await self._redis.xack(self._config.stream_name, self._config.group_name, message_id)
            return
        if self._interested_event_types is not None and event.event_type not in self._interested_event_types:
            await self._mark_processed(event)
            await self._redis.xack(self._config.stream_name, self._config.group_name, message_id)
            return
        route_key = str(event.metadata.get("route_key")) if event.metadata.get("route_key") is not None else None
        try:
            await self._invoke_handler(event)
        except Exception as exc:
            await self._record_consumer_metrics(
                route_key=route_key,
                occurred_at=event.occurred_at,
                succeeded=False,
                error=str(exc),
            )
            raise
        await self._mark_processed(event)
        await self._redis.xack(self._config.stream_name, self._config.group_name, message_id)
        await self._record_consumer_metrics(
            route_key=route_key,
            occurred_at=event.occurred_at,
            succeeded=True,
        )

    async def _record_consumer_metrics(
        self,
        *,
        route_key: str | None,
        occurred_at: datetime,
        succeeded: bool,
        error: str | None = None,
    ) -> None:
        if self._metrics_store is None:
            return
        await self._metrics_store.record_consumer_result(
            consumer_key=self._metrics_consumer_key,
            route_key=route_key,
            occurred_at=occurred_at,
            succeeded=succeeded,
            error=error,
        )

    async def run_async(self, *, stop_checker: Callable[[], bool] | None = None) -> None:
        await self._ensure_group()
        while not self._stop_requested and not (stop_checker() if stop_checker is not None else False):
            try:
                messages = await self._iter_stale_messages()
                if not messages:
                    messages = await self._iter_new_messages()
                if not messages:
                    continue
                for message_id, fields in messages:
                    await self._process_message(message_id, fields)
            except RedisError as exc:  # pragma: no cover
                LOGGER.warning(
                    "Event consumer group=%s consumer=%s error=%s",
                    self._config.group_name,
                    self._config.consumer_name,
                    exc,
                )
                await asyncio.sleep(1.0)
            except Exception as exc:  # pragma: no cover
                LOGGER.exception(
                    "Event consumer group=%s consumer=%s handler failed: %s",
                    self._config.group_name,
                    self._config.consumer_name,
                    exc,
                )
                await asyncio.sleep(0.5)

    def run(self, *, stop_checker: Callable[[], bool] | None = None) -> None:
        asyncio.run(self.run_async(stop_checker=stop_checker))

    async def close_async(self) -> None:
        await self._redis.aclose()

    def close(self) -> None:
        asyncio.run(self.close_async())


def default_consumer_name(group_name: str) -> str:
    return f"{group_name}-{socket.gethostname()}-{os.getpid()}"
