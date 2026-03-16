import asyncio
from contextlib import asynccontextmanager
from threading import Lock
from collections.abc import AsyncIterator

from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import LockError

from src.core.settings import get_settings

_async_redis_client: AsyncRedis | None = None
_async_redis_loop: asyncio.AbstractEventLoop | None = None
_async_redis_client_lock = Lock()


async def get_async_lock_redis() -> AsyncRedis:
    global _async_redis_client, _async_redis_loop
    current_loop = asyncio.get_running_loop()
    if _async_redis_client is None or _async_redis_loop is not current_loop:
        with _async_redis_client_lock:
            if _async_redis_client is None or _async_redis_loop is not current_loop:
                settings = get_settings()
                _async_redis_client = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
                _async_redis_loop = current_loop
    return _async_redis_client


@asynccontextmanager
async def async_redis_task_lock(
    name: str,
    *,
    timeout: int,
) -> AsyncIterator[bool]:
    lock = (await get_async_lock_redis()).lock(
        name=name,
        timeout=timeout,
        blocking=False,
        thread_local=False,
    )
    acquired = await lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if not acquired:
            return
        try:
            await lock.release()
        except LockError:
            pass


async def close_async_task_lock_client() -> None:
    global _async_redis_client, _async_redis_loop
    if _async_redis_client is None:
        return
    await _async_redis_client.aclose()
    _async_redis_client = None
    _async_redis_loop = None


async def ping_redis() -> None:
    await (await get_async_lock_redis()).ping()


async def wait_for_redis() -> None:
    settings = get_settings()
    last_error: Exception | None = None
    for _ in range(settings.redis_connect_retries):
        try:
            await ping_redis()
            return
        except Exception as exc:  # pragma: no cover
            last_error = exc
            await asyncio.sleep(settings.redis_connect_retry_delay)
    if last_error is not None:
        raise last_error
