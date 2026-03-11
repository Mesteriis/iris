from __future__ import annotations

import logging
import queue
import threading
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.settings import get_settings
from app.runtime.streams.types import build_event_fields

LOGGER = logging.getLogger(__name__)
_QUEUE_WAIT_SECONDS = 0.25


class RedisEventPublisher:
    def __init__(self, redis_url: str, *, stream_name: str) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._stream_name = stream_name
        self._queue: queue.SimpleQueue[dict[str, str] | None] = queue.SimpleQueue()
        self._drain_lock = threading.Lock()
        self._pending = 0
        self._pending_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="iris-event-publisher",
        )
        self._thread.start()

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        fields = build_event_fields(event_type, payload)
        with self._drain_lock:
            self._pending += 1
            self._pending_event.clear()
        self._queue.put(fields)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=_QUEUE_WAIT_SECONDS)
            except queue.Empty:
                continue
            if item is None:
                break
            try:
                self._redis.xadd(self._stream_name, fields=item)
            except RedisError as exc:  # pragma: no cover
                LOGGER.warning("Event publish failed for %s: %s", item.get("event_type"), exc)
            finally:
                with self._drain_lock:
                    self._pending = max(self._pending - 1, 0)
                    if self._pending == 0:
                        self._pending_event.set()

    def flush(self, timeout: float = 5.0) -> bool:
        with self._drain_lock:
            if self._pending == 0:
                return True
        return self._pending_event.wait(timeout=timeout)

    def close(self) -> None:
        self._stop_event.set()
        self._queue.put(None)
        self._thread.join(timeout=2.0)
        self._redis.close()


_publisher: RedisEventPublisher | None = None


def get_event_publisher() -> RedisEventPublisher:
    global _publisher
    if _publisher is None:
        settings = get_settings()
        _publisher = RedisEventPublisher(settings.redis_url, stream_name=settings.event_stream_name)
    return _publisher


def publish_event(event_type: str, payload: dict[str, Any]) -> None:
    get_event_publisher().publish(event_type, payload)


def flush_publisher(timeout: float = 5.0) -> bool:
    return get_event_publisher().flush(timeout=timeout)


def reset_event_publisher() -> None:
    global _publisher
    if _publisher is None:
        return
    _publisher.close()
    _publisher = None
