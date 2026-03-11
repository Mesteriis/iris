from __future__ import annotations

import time
from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from redis import Redis
from redis.exceptions import LockError

from app.core.config import get_settings

_redis_client: Redis | None = None
_redis_client_lock = Lock()


def get_lock_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        with _redis_client_lock:
            if _redis_client is None:
                settings = get_settings()
                _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


@contextmanager
def redis_task_lock(
    name: str,
    *,
    timeout: int,
) -> Iterator[bool]:
    lock = get_lock_redis().lock(
        name=name,
        timeout=timeout,
        blocking=False,
        thread_local=False,
    )
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if not acquired:
            return
        try:
            lock.release()
        except LockError:
            pass


def close_task_lock_client() -> None:
    global _redis_client
    if _redis_client is None:
        return
    _redis_client.close()
    _redis_client = None


def ping_redis() -> None:
    get_lock_redis().ping()


def wait_for_redis() -> None:
    settings = get_settings()
    last_error: Exception | None = None
    for _ in range(settings.redis_connect_retries):
        try:
            ping_redis()
            return
        except Exception as exc:  # pragma: no cover
            last_error = exc
            time.sleep(settings.redis_connect_retry_delay)
    if last_error is not None:
        raise last_error
