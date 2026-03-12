from __future__ import annotations

from types import SimpleNamespace

import pytest
from redis.exceptions import LockError

from app.runtime.orchestration import dispatcher, locks


@pytest.mark.asyncio
async def test_dispatcher_enqueues_tasks_locally() -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class Task:
        async def kiq(self, *args: object, **kwargs: object) -> None:
            calls.append((args, kwargs))

    task = Task()
    await dispatcher.enqueue_task(task, 1, 2, source="scheduler")
    await dispatcher.dispatch_task_locally(object(), task, 3, source="local")

    assert calls == [
        ((1, 2), {"source": "scheduler"}),
        ((3,), {"source": "local"}),
    ]


class _FakeLock:
    def __init__(self, *, acquired: bool = True, release_error: Exception | None = None) -> None:
        self.acquired = acquired
        self.release_error = release_error
        self.acquire_calls: list[bool] = []
        self.released = False

    async def acquire(self, blocking: bool = False) -> bool:
        self.acquire_calls.append(blocking)
        return self.acquired

    async def release(self) -> None:
        self.released = True
        if self.release_error is not None:
            raise self.release_error


class _FakeRedis:
    def __init__(self, *, lock: _FakeLock | None = None) -> None:
        self.lock_instance = lock or _FakeLock()
        self.lock_calls: list[dict[str, object]] = []
        self.closed = False
        self.ping_calls = 0

    def lock(self, **kwargs: object) -> _FakeLock:
        self.lock_calls.append(kwargs)
        return self.lock_instance

    async def aclose(self) -> None:
        self.closed = True

    async def ping(self) -> None:
        self.ping_calls += 1


@pytest.mark.asyncio
async def test_async_lock_client_singleton_and_close(monkeypatch) -> None:
    locks._async_redis_client = None
    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        locks,
        "get_settings",
        lambda: SimpleNamespace(
            redis_url="redis://test",
            redis_connect_retries=2,
            redis_connect_retry_delay=0.0,
        ),
    )
    monkeypatch.setattr(locks.AsyncRedis, "from_url", lambda *args, **kwargs: fake_redis)

    client_a = await locks.get_async_lock_redis()
    client_b = await locks.get_async_lock_redis()

    assert client_a is fake_redis
    assert client_b is fake_redis

    await locks.close_async_task_lock_client()

    assert fake_redis.closed is True
    assert locks._async_redis_client is None

    await locks.close_async_task_lock_client()


@pytest.mark.asyncio
async def test_async_lock_client_double_checked_branch(monkeypatch) -> None:
    fake_redis = _FakeRedis()

    class LockStub:
        def __enter__(self):
            locks._async_redis_client = fake_redis
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    locks._async_redis_client = None
    monkeypatch.setattr(locks, "_async_redis_client_lock", LockStub())

    client = await locks.get_async_lock_redis()

    assert client is fake_redis


@pytest.mark.asyncio
async def test_async_redis_task_lock_branches(monkeypatch) -> None:
    acquired_lock = _FakeLock(acquired=True)
    fake_redis = _FakeRedis(lock=acquired_lock)

    async def get_fake_redis() -> _FakeRedis:
        return fake_redis

    monkeypatch.setattr(locks, "get_async_lock_redis", get_fake_redis)

    async with locks.async_redis_task_lock("iris:test", timeout=15) as acquired:
        assert acquired is True

    assert fake_redis.lock_calls == [
        {
            "name": "iris:test",
            "timeout": 15,
            "blocking": False,
            "thread_local": False,
        }
    ]
    assert acquired_lock.acquire_calls == [False]
    assert acquired_lock.released is True

    skipped_lock = _FakeLock(acquired=False)

    async def get_skipped_redis() -> _FakeRedis:
        return _FakeRedis(lock=skipped_lock)

    monkeypatch.setattr(locks, "get_async_lock_redis", get_skipped_redis)
    async with locks.async_redis_task_lock("iris:test:skip", timeout=5) as acquired:
        assert acquired is False
    assert skipped_lock.released is False

    errored_lock = _FakeLock(acquired=True, release_error=LockError("already released"))

    async def get_errored_redis() -> _FakeRedis:
        return _FakeRedis(lock=errored_lock)

    monkeypatch.setattr(locks, "get_async_lock_redis", get_errored_redis)
    async with locks.async_redis_task_lock("iris:test:error", timeout=5) as acquired:
        assert acquired is True
    assert errored_lock.released is True


@pytest.mark.asyncio
async def test_wait_for_redis_success_and_retry_failure(monkeypatch) -> None:
    original_ping_redis = locks.ping_redis

    async def fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(locks.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(
        locks,
        "get_settings",
        lambda: SimpleNamespace(
            redis_connect_retries=3,
            redis_connect_retry_delay=0.0,
        ),
    )

    success_calls: list[str] = []

    async def ping_success() -> None:
        success_calls.append("ok")

    monkeypatch.setattr(locks, "ping_redis", ping_success)
    await locks.wait_for_redis()
    assert success_calls == ["ok"]

    fake_ping_redis = _FakeRedis()

    async def get_fake_redis() -> _FakeRedis:
        return fake_ping_redis

    monkeypatch.setattr(locks, "get_async_lock_redis", get_fake_redis)
    monkeypatch.setattr(locks, "ping_redis", original_ping_redis)
    await locks.ping_redis()
    assert fake_ping_redis.ping_calls == 1

    failure_calls: list[str] = []

    async def ping_failure() -> None:
        failure_calls.append("boom")
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(locks, "ping_redis", ping_failure)
    with pytest.raises(RuntimeError, match="redis unavailable"):
        await locks.wait_for_redis()
    assert failure_calls == ["boom", "boom", "boom"]

    monkeypatch.setattr(
        locks,
        "get_settings",
        lambda: SimpleNamespace(
            redis_connect_retries=0,
            redis_connect_retry_delay=0.0,
        ),
    )
    await locks.wait_for_redis()
