from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol, cast

from redis.asyncio import Redis as AsyncRedis

from iris.core.settings import get_settings

settings = get_settings()
ROUTE_METRIC_KEY_PREFIX = "iris:control_plane:metrics:route"
CONSUMER_METRIC_KEY_PREFIX = "iris:control_plane:metrics:consumer"


class _AsyncHashClient(Protocol):
    async def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        del name, key, amount
        return 0

    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | None = None,
        mapping: Mapping[str, str] | None = None,
    ) -> int: ...

    async def hgetall(self, name: str) -> dict[str, str]: ...

    async def hget(self, name: str, key: str) -> str | None: ...


@lru_cache(maxsize=1)
def get_async_control_plane_metrics_client() -> AsyncRedis:
    return cast(AsyncRedis, AsyncRedis.from_url(settings.redis_url, decode_responses=True))


def route_metric_key(route_key: str) -> str:
    return f"{ROUTE_METRIC_KEY_PREFIX}:{route_key}"


def consumer_metric_key(consumer_key: str) -> str:
    return f"{CONSUMER_METRIC_KEY_PREFIX}:{consumer_key}"


class ControlPlaneMetricsStore:
    def __init__(self, client: AsyncRedis | None = None) -> None:
        self._client: _AsyncHashClient = cast(_AsyncHashClient, client or get_async_control_plane_metrics_client())

    async def record_route_dispatch(
        self,
        *,
        route_key: str,
        consumer_key: str,
        delivered: bool,
        shadow: bool,
        reason: str,
        occurred_at: datetime,
    ) -> None:
        key = route_metric_key(route_key)
        await self._client.hincrby(key, "evaluated_total", 1)
        if delivered:
            await self._client.hincrby(key, "delivered_total", 1)
            await self._client.hset(key, "last_delivered_at", self._iso(occurred_at))
        else:
            await self._client.hincrby(key, "skipped_total", 1)
        if shadow:
            await self._client.hincrby(key, "shadow_total", 1)
        await self._client.hset(
            key,
            mapping={
                "consumer_key": consumer_key,
                "last_reason": reason,
                "last_evaluated_at": self._iso(occurred_at),
            },
        )

    async def record_consumer_result(
        self,
        *,
        consumer_key: str,
        route_key: str | None,
        occurred_at: datetime,
        succeeded: bool,
        error: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        consumer_key_name = consumer_metric_key(consumer_key)
        latency_ms = max((now - occurred_at).total_seconds() * 1000.0, 0.0)
        await self._client.hincrby(consumer_key_name, "processed_total", 1)
        await self._client.hset(consumer_key_name, "last_seen_at", self._iso(now))
        await self._client.hset(consumer_key_name, "latency_total_ms", str(float(await self._float_hget(consumer_key_name, "latency_total_ms")) + latency_ms))
        await self._client.hset(consumer_key_name, "latency_count", str(int(await self._int_hget(consumer_key_name, "latency_count")) + 1))
        if succeeded:
            await self._client.hincrby(consumer_key_name, "success_total", 1)
        else:
            await self._client.hincrby(consumer_key_name, "failure_total", 1)
            if error is not None:
                await self._client.hset(consumer_key_name, "last_error", error[:255])
            await self._client.hset(consumer_key_name, "last_failure_at", self._iso(now))
        if route_key is None:
            return
        route_key_name = route_metric_key(route_key)
        await self._client.hset(route_key_name, "consumer_key", consumer_key)
        await self._client.hset(route_key_name, "last_completed_at", self._iso(now))
        await self._client.hset(route_key_name, "latency_total_ms", str(float(await self._float_hget(route_key_name, "latency_total_ms")) + latency_ms))
        await self._client.hset(route_key_name, "latency_count", str(int(await self._int_hget(route_key_name, "latency_count")) + 1))
        if succeeded:
            await self._client.hincrby(route_key_name, "success_total", 1)
        else:
            await self._client.hincrby(route_key_name, "failure_total", 1)
            if error is not None:
                await self._client.hset(route_key_name, "last_error", error[:255])

    async def read_route_metrics(self, route_key: str) -> dict[str, str]:
        return dict(await self._client.hgetall(route_metric_key(route_key)))

    async def read_consumer_metrics(self, consumer_key: str) -> dict[str, str]:
        return dict(await self._client.hgetall(consumer_metric_key(consumer_key)))

    async def _float_hget(self, key: str, field: str) -> float:
        raw = await self._client.hget(key, field)
        return float(raw) if raw is not None else 0.0

    async def _int_hget(self, key: str, field: str) -> int:
        raw = await self._client.hget(key, field)
        return int(raw) if raw is not None else 0

    def _iso(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat()


__all__ = [
    "CONSUMER_METRIC_KEY_PREFIX",
    "ROUTE_METRIC_KEY_PREFIX",
    "ControlPlaneMetricsStore",
    "consumer_metric_key",
    "get_async_control_plane_metrics_client",
    "route_metric_key",
]
