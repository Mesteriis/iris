import asyncio
import json
from functools import lru_cache
from typing import Any
from weakref import WeakKeyDictionary

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from src.core.settings import get_settings

PORTFOLIO_STATE_CACHE_KEY = "iris:portfolio:state"
PORTFOLIO_BALANCES_CACHE_KEY = "iris:portfolio:balances"
PORTFOLIO_CACHE_TTL_SECONDS = 60 * 60 * 24
_ASYNC_PORTFOLIO_CACHE_CLIENTS: WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncRedis] = WeakKeyDictionary()


# NOTE:
# This synchronous cache client remains intentionally for legacy sync-only code
# and tests outside the main async request/runtime path.
@lru_cache(maxsize=1)
def get_portfolio_cache_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_async_portfolio_cache_client() -> AsyncRedis:
    settings = get_settings()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    client = _ASYNC_PORTFOLIO_CACHE_CLIENTS.get(loop)
    if client is None:
        client = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
        _ASYNC_PORTFOLIO_CACHE_CLIENTS[loop] = client
    return client


def _clear_async_portfolio_cache_clients() -> None:
    _ASYNC_PORTFOLIO_CACHE_CLIENTS.clear()


setattr(get_async_portfolio_cache_client, "cache_clear", _clear_async_portfolio_cache_clients)


def _serialize_payload(payload: list[dict[str, Any]] | dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _parse_portfolio_state(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_portfolio_balances(raw: str) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, list) else None


def cache_portfolio_state(payload: dict[str, Any]) -> None:
    get_portfolio_cache_client().set(
        PORTFOLIO_STATE_CACHE_KEY,
        _serialize_payload(payload),
        ex=PORTFOLIO_CACHE_TTL_SECONDS,
    )


async def cache_portfolio_state_async(payload: dict[str, Any]) -> None:
    await get_async_portfolio_cache_client().set(
        PORTFOLIO_STATE_CACHE_KEY,
        _serialize_payload(payload),
        ex=PORTFOLIO_CACHE_TTL_SECONDS,
    )


def read_cached_portfolio_state() -> dict[str, Any] | None:
    raw = get_portfolio_cache_client().get(PORTFOLIO_STATE_CACHE_KEY)
    if raw is None:
        return None
    return _parse_portfolio_state(raw)


async def read_cached_portfolio_state_async() -> dict[str, Any] | None:
    raw = await get_async_portfolio_cache_client().get(PORTFOLIO_STATE_CACHE_KEY)
    if raw is None:
        return None
    return _parse_portfolio_state(raw)


def cache_portfolio_balances(payload: list[dict[str, Any]]) -> None:
    get_portfolio_cache_client().set(
        PORTFOLIO_BALANCES_CACHE_KEY,
        _serialize_payload(payload),
        ex=PORTFOLIO_CACHE_TTL_SECONDS,
    )


async def cache_portfolio_balances_async(payload: list[dict[str, Any]]) -> None:
    await get_async_portfolio_cache_client().set(
        PORTFOLIO_BALANCES_CACHE_KEY,
        _serialize_payload(payload),
        ex=PORTFOLIO_CACHE_TTL_SECONDS,
    )


def read_cached_portfolio_balances() -> list[dict[str, Any]] | None:
    raw = get_portfolio_cache_client().get(PORTFOLIO_BALANCES_CACHE_KEY)
    if raw is None:
        return None
    return _parse_portfolio_balances(raw)


async def read_cached_portfolio_balances_async() -> list[dict[str, Any]] | None:
    raw = await get_async_portfolio_cache_client().get(PORTFOLIO_BALANCES_CACHE_KEY)
    if raw is None:
        return None
    return _parse_portfolio_balances(raw)
