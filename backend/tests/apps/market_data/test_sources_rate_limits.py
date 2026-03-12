from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from redis.exceptions import RedisError, WatchError

from app.apps.market_data.sources import rate_limits
from app.apps.market_data.sources.base import RateLimitedMarketSourceError


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.operations: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def watch(self, key: str) -> None:
        del key
        if self.redis.watch_failures > 0:
            self.redis.watch_failures -= 1
            raise WatchError("retry")
        if self.redis.error_on_watch:
            raise RedisError("watch failed")

    async def get(self, key: str):
        if self.redis.error_on_get:
            raise RedisError("get failed")
        return self.redis.values.get(key)

    async def pttl(self, key: str):
        if self.redis.error_on_pttl:
            raise RedisError("pttl failed")
        return self.redis.ttls_ms.get(key, -1)

    def multi(self) -> None:
        return None

    def set(self, key: str, value: object, *, ex: int | None = None, px: int | None = None) -> None:
        self.operations.append(("set", (key, value), {"ex": ex, "px": px}))

    def incrby(self, key: str, amount: int) -> None:
        self.operations.append(("incrby", (key, amount), {}))

    async def execute(self) -> None:
        if self.redis.error_on_execute:
            raise RedisError("execute failed")
        for op, args, kwargs in self.operations:
            if op == "set":
                key, value = args
                self.redis.values[key] = value
                if kwargs["ex"] is not None:
                    self.redis.ttls_ms[key] = int(kwargs["ex"]) * 1000
                if kwargs["px"] is not None:
                    self.redis.ttls_ms[key] = int(kwargs["px"])
            elif op == "incrby":
                key, amount = args
                current = int(self.redis.values.get(key) or 0)
                self.redis.values[key] = current + amount

    async def reset(self) -> None:
        self.redis.reset_calls += 1
        self.operations.clear()


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.ttls_ms: dict[str, int] = {}
        self.watch_failures = 0
        self.error_on_watch = False
        self.error_on_get = False
        self.error_on_pttl = False
        self.error_on_execute = False
        self.reset_calls = 0
        self.set_calls: list[tuple[str, object, int | None, int | None]] = []
        self.delete_calls: list[str] = []

    async def pttl(self, key: str) -> int:
        if self.error_on_pttl:
            raise RedisError("pttl failed")
        return self.ttls_ms.get(key, -1)

    async def set(self, key: str, value: object, *, ex: int | None = None, px: int | None = None) -> None:
        self.set_calls.append((key, value, ex, px))
        self.values[key] = value
        if ex is not None:
            self.ttls_ms[key] = ex * 1000
        if px is not None:
            self.ttls_ms[key] = px

    async def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self.values.pop(key, None)
        self.ttls_ms.pop(key, None)

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


class FakeManager:
    def __init__(self) -> None:
        self.wait_calls: list[tuple[str, object, int | None]] = []
        self.cooldown_calls: list[tuple[str, int]] = []

    async def wait_for_slot(self, source_name: str, policy, *, cost: int | None = None) -> None:
        self.wait_calls.append((source_name, policy, cost))

    async def set_cooldown(self, source_name: str, seconds: int) -> None:
        self.cooldown_calls.append((source_name, seconds))


class FakeClient:
    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object] | None, dict[str, str] | None]] = []

    async def get(self, url: str, *, params=None, headers=None):
        self.calls.append((url, params, headers))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _response(
    *,
    status_code: int = 200,
    payload: object | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        headers=headers,
        request=httpx.Request("GET", "https://example.com"),
    )


@pytest.mark.asyncio
async def test_rate_limit_policy_and_retry_after_parsing() -> None:
    assert rate_limits.get_rate_limit_policy("binance").request_cost == 2
    assert rate_limits.get_rate_limit_policy("unknown").fallback_retry_after_seconds == 60
    assert rate_limits._parse_retry_after_seconds(_response(headers={"Retry-After": "4"}), 9) == 4
    assert rate_limits._parse_retry_after_seconds(_response(headers={"gw-ratelimit-reset": "2100"}), 9) == 3
    assert rate_limits._parse_retry_after_seconds(_response(headers={"Retry-After": "bad"}), 9) == 9


@pytest.mark.asyncio
async def test_rate_limit_manager_cooldown_snapshot_and_singleton(monkeypatch) -> None:
    redis = FakeRedis()
    manager = rate_limits.RedisRateLimitManager()
    fixed_now = datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(rate_limits, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=redis))
    monkeypatch.setattr(rate_limits, "utc_now", lambda: fixed_now)

    await manager.set_cooldown("polygon", 7)
    assert await manager.cooldown_seconds("polygon") == 7.0
    assert await manager.is_rate_limited("polygon") is True

    snapshot = await manager.snapshot("polygon")
    assert snapshot.source_name == "polygon"
    assert snapshot.cooldown_seconds == 7.0
    assert snapshot.next_available_at == fixed_now.replace(microsecond=0) + rate_limits.timedelta(seconds=7)

    await manager.clear_cooldown("polygon")
    assert redis.delete_calls == ["iris:rate-limit:polygon:cooldown"]

    redis.error_on_pttl = True
    assert await manager.cooldown_seconds("polygon") == 0.0

    redis.error_on_pttl = False
    error_redis = FakeRedis()
    error_redis.error_on_watch = False

    async def failing_set(*args, **kwargs):
        raise RedisError("set failed")

    async def failing_delete(*args, **kwargs):
        raise RedisError("delete failed")

    error_redis.set = failing_set  # type: ignore[method-assign]
    error_redis.delete = failing_delete  # type: ignore[method-assign]
    monkeypatch.setattr(rate_limits, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=error_redis))
    await manager.set_cooldown("polygon", 3)
    await manager.clear_cooldown("polygon")

    rate_limits._rate_limit_manager = None
    first = rate_limits.get_rate_limit_manager()
    second = rate_limits.get_rate_limit_manager()
    assert first is second

    class LockProxy:
        def __enter__(self):
            rate_limits._rate_limit_manager = first
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    rate_limits._rate_limit_manager = None
    monkeypatch.setattr(rate_limits, "_rate_limit_manager_lock", LockProxy())
    assert rate_limits.get_rate_limit_manager() is first


@pytest.mark.asyncio
async def test_rate_limit_manager_wait_for_slot(monkeypatch) -> None:
    manager = rate_limits.RedisRateLimitManager()
    sleeps: list[float] = []
    cooldown_values = iter([0.3, 0.0, 0.0, 0.0])
    quota_values = iter([0.4, 0.0, 0.0])
    interval_values = iter([0.2])

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def fake_cooldown(_source_name: str) -> float:
        return next(cooldown_values)

    async def fake_quota(_source_name: str, _policy, _cost: int) -> float:
        return next(quota_values)

    async def fake_interval(_source_name: str, _policy) -> float:
        return next(interval_values)

    monkeypatch.setattr(rate_limits.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(manager, "cooldown_seconds", fake_cooldown)
    monkeypatch.setattr(manager, "_reserve_quota", fake_quota)
    monkeypatch.setattr(manager, "_reserve_interval", fake_interval)

    await manager.wait_for_slot("binance", rate_limits.get_rate_limit_policy("binance"), cost=5)
    assert sleeps == [0.3, 0.4, 0.2]

    sleeps.clear()
    
    async def zero_cooldown(_source_name: str) -> float:
        return 0.0

    async def zero_quota(*_args) -> float:
        return 0.0

    async def zero_interval(*_args) -> float:
        return 0.0

    monkeypatch.setattr(manager, "cooldown_seconds", zero_cooldown)
    monkeypatch.setattr(manager, "_reserve_quota", zero_quota)
    monkeypatch.setattr(manager, "_reserve_interval", zero_interval)
    await manager.wait_for_slot("binance", rate_limits.get_rate_limit_policy("binance"), cost=1)
    assert sleeps == []


@pytest.mark.asyncio
async def test_rate_limit_manager_reserve_quota_paths(monkeypatch) -> None:
    redis = FakeRedis()
    manager = rate_limits.RedisRateLimitManager()
    cooldown_calls: list[tuple[str, int]] = []
    policy = rate_limits.RateLimitPolicy(requests_per_window=5, window_seconds=10, request_cost=1)

    monkeypatch.setattr(rate_limits, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=redis))

    async def fake_set_cooldown(source_name: str, seconds: int) -> None:
        cooldown_calls.append((source_name, seconds))

    monkeypatch.setattr(manager, "set_cooldown", fake_set_cooldown)

    assert await manager._reserve_quota("binance", rate_limits.RateLimitPolicy(), 2) == 0.0

    delay = await manager._reserve_quota("binance", policy, 2)
    assert delay == 0.0
    assert redis.values["iris:rate-limit:binance:quota"] == 2

    delay = await manager._reserve_quota("binance", policy, 2)
    assert delay == 0.0
    assert redis.values["iris:rate-limit:binance:quota"] == 4

    redis.ttls_ms["iris:rate-limit:binance:quota"] = 2500
    delay = await manager._reserve_quota("binance", policy, 2)
    assert delay == 2.5
    assert cooldown_calls == [("binance", 3)]

    retry_redis = FakeRedis()
    retry_redis.watch_failures = 1
    monkeypatch.setattr(rate_limits, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=retry_redis))
    assert await manager._reserve_quota("binance", policy, 1) == 0.0
    assert retry_redis.values["iris:rate-limit:binance:quota"] == 1

    error_redis = FakeRedis()
    error_redis.error_on_watch = True
    monkeypatch.setattr(rate_limits, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=error_redis))
    assert await manager._reserve_quota("binance", policy, 1) == 0.0


@pytest.mark.asyncio
async def test_rate_limit_manager_reserve_interval_paths(monkeypatch) -> None:
    manager = rate_limits.RedisRateLimitManager()
    fixed_now = datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(rate_limits, "utc_now", lambda: fixed_now)

    redis = FakeRedis()
    monkeypatch.setattr(rate_limits, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=redis))

    assert await manager._reserve_interval("kraken", rate_limits.RateLimitPolicy()) == 0.0

    policy = rate_limits.RateLimitPolicy(min_interval_seconds=0.5)
    assert await manager._reserve_interval("kraken", policy) == 0.0
    assert redis.values["iris:rate-limit:kraken:interval"] == int(fixed_now.timestamp() * 1000) + 500

    redis.values["iris:rate-limit:kraken:interval"] = int(fixed_now.timestamp() * 1000) + 800
    assert await manager._reserve_interval("kraken", policy) == pytest.approx(0.8, rel=0.01)

    retry_redis = FakeRedis()
    retry_redis.watch_failures = 1
    monkeypatch.setattr(rate_limits, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=retry_redis))
    assert await manager._reserve_interval("kraken", policy) == 0.0

    error_redis = FakeRedis()
    error_redis.error_on_execute = True
    monkeypatch.setattr(rate_limits, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=error_redis))
    assert await manager._reserve_interval("kraken", policy) == 0.0


@pytest.mark.asyncio
async def test_rate_limited_get_success_rate_limit_and_http_error(monkeypatch) -> None:
    manager = FakeManager()
    monkeypatch.setattr(rate_limits, "get_rate_limit_manager", lambda: manager)

    success_client = FakeClient(_response(status_code=200, payload={"ok": True}))
    response = await rate_limits.rate_limited_get(
        "coinbase",
        success_client,
        "https://example.com",
        params={"limit": 1},
        headers={"X-Test": "1"},
        cost=3,
    )
    assert response.status_code == 200
    assert manager.wait_calls[0][0] == "coinbase"
    assert manager.wait_calls[0][2] == 3
    assert success_client.calls == [("https://example.com", {"limit": 1}, {"X-Test": "1"})]

    limited_client = FakeClient(_response(status_code=429, payload={"detail": "slow"}, headers={"Retry-After": "6"}))
    with pytest.raises(RateLimitedMarketSourceError) as exc_info:
        await rate_limits.rate_limited_get("coinbase", limited_client, "https://example.com")
    assert exc_info.value.retry_after_seconds == 6
    assert manager.cooldown_calls == [("coinbase", 6)]

    error_client = FakeClient(httpx.ConnectError("boom"))
    with pytest.raises(httpx.ConnectError):
        await rate_limits.rate_limited_get("coinbase", error_client, "https://example.com")
