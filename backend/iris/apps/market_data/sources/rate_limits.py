import asyncio
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from typing import Protocol, cast

import httpx
from redis.exceptions import RedisError, WatchError

from iris.apps.market_data.domain import utc_now
from iris.runtime.orchestration.locks import get_async_lock_redis


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    requests_per_window: int | None = None
    window_seconds: int | None = None
    min_interval_seconds: float = 0.0
    request_cost: int = 1
    fallback_retry_after_seconds: int = 60
    official_limit: bool = True


@dataclass(frozen=True, slots=True)
class RateLimitSnapshot:
    source_name: str
    cooldown_seconds: float
    next_available_at: datetime | None
    policy: RateLimitPolicy


HttpQueryScalar = str | int | float | bool | None
HttpQueryValue = HttpQueryScalar | Sequence[HttpQueryScalar]
HttpQueryParams = Mapping[str, HttpQueryValue]


class _RedisPipeline(Protocol):
    async def watch(self, key: str) -> None: ...
    async def get(self, key: str) -> object: ...
    async def pttl(self, key: str) -> int: ...
    def multi(self) -> None: ...
    def set(self, key: str, value: int, *, ex: int | None = None, px: int | None = None) -> None:
        del key, value, ex, px

    def incrby(self, key: str, amount: int) -> None:
        del key, amount

    async def execute(self) -> None: ...
    async def reset(self) -> None: ...


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


SOURCE_RATE_LIMIT_POLICIES: dict[str, RateLimitPolicy] = {
    # Binance Spot docs:
    # - Global REQUEST_WEIGHT shown by exchangeInfo is 6000/minute.
    # - GET /api/v3/klines has request weight 2.
    "binance": RateLimitPolicy(
        requests_per_window=6000,
        window_seconds=60,
        request_cost=2,
        fallback_retry_after_seconds=60,
    ),
    # Coinbase Exchange docs: public REST endpoints are 10 rps per IP.
    "coinbase": RateLimitPolicy(
        requests_per_window=10,
        window_seconds=1,
        min_interval_seconds=0.1,
        fallback_retry_after_seconds=1,
    ),
    # Polygon/Massive free docs surface 5 API calls/minute on public market data pages.
    "polygon": RateLimitPolicy(
        requests_per_window=5,
        window_seconds=60,
        min_interval_seconds=12.0,
        fallback_retry_after_seconds=60,
    ),
    # Kraken public OHLC docs do not publish a clear unauthenticated per-IP number.
    # Keep a conservative client-side pace and still honor provider throttling responses.
    "kraken": RateLimitPolicy(
        min_interval_seconds=1.0,
        fallback_retry_after_seconds=5,
        official_limit=False,
    ),
    # KuCoin docs: Public pool 2000/30s, Get Klines weight 3.
    "kucoin": RateLimitPolicy(
        requests_per_window=2000,
        window_seconds=30,
        request_cost=3,
        fallback_retry_after_seconds=30,
    ),
    # Twelve Data Basic pricing: 8 API credits and 800/day.
    "twelvedata": RateLimitPolicy(
        requests_per_window=8,
        window_seconds=60,
        min_interval_seconds=7.5,
        fallback_retry_after_seconds=60,
    ),
    # Alpha Vantage support page currently documents free tier as 25 requests/day.
    "alphavantage": RateLimitPolicy(
        requests_per_window=25,
        window_seconds=86400,
        fallback_retry_after_seconds=300,
    ),
    # CoinGecko docs: demo/public rate limit is ~30 calls/minute.
    "coingecko": RateLimitPolicy(
        requests_per_window=30,
        window_seconds=60,
        min_interval_seconds=2.0,
        fallback_retry_after_seconds=60,
    ),
    # No official numeric public limit found for ISS MOEX.
    "moex": RateLimitPolicy(
        min_interval_seconds=0.5,
        fallback_retry_after_seconds=60,
        official_limit=False,
    ),
    # Yahoo Finance chart endpoint used here is unofficial/publicly undocumented.
    "yahoo": RateLimitPolicy(
        min_interval_seconds=2.0,
        fallback_retry_after_seconds=300,
        official_limit=False,
    ),
}


def get_rate_limit_policy(source_name: str) -> RateLimitPolicy:
    return SOURCE_RATE_LIMIT_POLICIES.get(source_name, RateLimitPolicy())


def _parse_retry_after_seconds(response: httpx.Response, fallback: int) -> int:
    retry_after = response.headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return max(int(retry_after), 1)

    kucoin_reset = response.headers.get("gw-ratelimit-reset")
    if kucoin_reset and kucoin_reset.isdigit():
        return max(math.ceil(int(kucoin_reset) / 1000), 1)

    return max(fallback, 1)


class RedisRateLimitManager:
    def __init__(self) -> None:
        self._local_lock = Lock()

    def _cooldown_key(self, source_name: str) -> str:
        return f"iris:rate-limit:{source_name}:cooldown"

    def _quota_key(self, source_name: str) -> str:
        return f"iris:rate-limit:{source_name}:quota"

    def _interval_key(self, source_name: str) -> str:
        return f"iris:rate-limit:{source_name}:interval"

    async def cooldown_seconds(self, source_name: str) -> float:
        try:
            ttl_ms = await (await get_async_lock_redis()).pttl(self._cooldown_key(source_name))
        except RedisError:
            return 0.0
        return max(ttl_ms, 0) / 1000 if ttl_ms and ttl_ms > 0 else 0.0

    async def is_rate_limited(self, source_name: str) -> bool:
        return await self.cooldown_seconds(source_name) > 0

    async def snapshot(self, source_name: str) -> RateLimitSnapshot:
        cooldown_seconds = await self.cooldown_seconds(source_name)
        next_available_at = utc_now() + timedelta(seconds=cooldown_seconds) if cooldown_seconds > 0 else None
        return RateLimitSnapshot(
            source_name=source_name,
            cooldown_seconds=cooldown_seconds,
            next_available_at=next_available_at,
            policy=get_rate_limit_policy(source_name),
        )

    async def set_cooldown(self, source_name: str, seconds: int) -> None:
        duration = max(int(seconds), 1)
        try:
            await (await get_async_lock_redis()).set(self._cooldown_key(source_name), "1", ex=duration)
        except RedisError:
            return

    async def clear_cooldown(self, source_name: str) -> None:
        try:
            await (await get_async_lock_redis()).delete(self._cooldown_key(source_name))
        except RedisError:
            return

    async def wait_for_slot(self, source_name: str, policy: RateLimitPolicy, *, cost: int | None = None) -> None:
        effective_cost = max(cost or policy.request_cost, 1)

        while True:
            cooldown = await self.cooldown_seconds(source_name)
            if cooldown > 0:
                await asyncio.sleep(min(max(cooldown, 0.05), 5.0))
                continue

            quota_delay = await self._reserve_quota(source_name, policy, effective_cost)
            if quota_delay > 0:
                await asyncio.sleep(min(max(quota_delay, 0.05), 5.0))
                continue

            interval_delay = await self._reserve_interval(source_name, policy)
            if interval_delay > 0:
                await asyncio.sleep(min(max(interval_delay, 0.05), 5.0))
                return

            return

    async def _reserve_quota(self, source_name: str, policy: RateLimitPolicy, cost: int) -> float:
        if policy.requests_per_window is None or policy.window_seconds is None:
            return 0.0

        key = self._quota_key(source_name)
        redis = await get_async_lock_redis()

        while True:
            pipe = cast(_RedisPipeline, redis.pipeline())
            try:
                await pipe.watch(key)
                current_raw = await pipe.get(key)
                ttl_ms = await pipe.pttl(key)
                current = _coerce_int(current_raw)
                if current > 0 and current + cost > policy.requests_per_window:
                    await pipe.reset()
                    wait_seconds = max(ttl_ms, 1000) / 1000 if ttl_ms and ttl_ms > 0 else float(policy.window_seconds)
                    await self.set_cooldown(source_name, math.ceil(wait_seconds))
                    return wait_seconds

                pipe.multi()
                if current == 0:
                    pipe.set(key, cost, ex=max(policy.window_seconds, 1))
                else:
                    pipe.incrby(key, cost)
                await pipe.execute()
                return 0.0
            except WatchError:
                continue
            except RedisError:
                return 0.0
            finally:
                await pipe.reset()

    async def _reserve_interval(self, source_name: str, policy: RateLimitPolicy) -> float:
        if policy.min_interval_seconds <= 0:
            return 0.0

        interval_ms = max(int(policy.min_interval_seconds * 1000), 1)
        key = self._interval_key(source_name)
        redis = await get_async_lock_redis()

        while True:
            pipe = cast(_RedisPipeline, redis.pipeline())
            try:
                await pipe.watch(key)
                now_ms = int(utc_now().timestamp() * 1000)
                next_allowed_raw = await pipe.get(key)
                next_allowed_ms = _coerce_int(next_allowed_raw)
                base_ms = max(now_ms, next_allowed_ms)
                delay_ms = max(base_ms - now_ms, 0)
                expires_ms = max(interval_ms * 10, 1000)

                pipe.multi()
                pipe.set(key, base_ms + interval_ms, px=expires_ms)
                await pipe.execute()
                return delay_ms / 1000
            except WatchError:
                continue
            except RedisError:
                return 0.0
            finally:
                await pipe.reset()


_rate_limit_manager: RedisRateLimitManager | None = None
_rate_limit_manager_lock = Lock()


def get_rate_limit_manager() -> RedisRateLimitManager:
    global _rate_limit_manager
    if _rate_limit_manager is None:
        with _rate_limit_manager_lock:
            if _rate_limit_manager is None:
                _rate_limit_manager = RedisRateLimitManager()
    return _rate_limit_manager


async def rate_limited_get(
    source_name: str,
    client: httpx.AsyncClient,
    url: str,
    *,
    params: HttpQueryParams | None = None,
    headers: dict[str, str] | None = None,
    rate_limit_statuses: set[int] | None = None,
    fallback_retry_after_seconds: int | None = None,
    cost: int | None = None,
    rate_limit_identity: str | None = None,
) -> httpx.Response:
    from iris.apps.market_data.sources.base import RateLimitedMarketSourceError

    policy = get_rate_limit_policy(source_name)
    manager = get_rate_limit_manager()
    identity = rate_limit_identity or source_name
    await manager.wait_for_slot(identity, policy, cost=cost)

    try:
        response = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError:
        raise

    statuses = rate_limit_statuses or {429}
    if response.status_code in statuses:
        retry_after_seconds = _parse_retry_after_seconds(
            response,
            fallback_retry_after_seconds or policy.fallback_retry_after_seconds,
        )
        await manager.set_cooldown(identity, retry_after_seconds)
        raise RateLimitedMarketSourceError(
            source_name,
            retry_after_seconds,
            f"{source_name} rate limited",
        )

    return response
