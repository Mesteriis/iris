from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from weakref import WeakKeyDictionary

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from src.core.settings import get_settings
from src.apps.patterns.domain.regime import RegimeRead

REGIME_CACHE_PREFIX = "iris:regime"
REGIME_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7
_ASYNC_REGIME_CACHE_CLIENTS: "WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncRedis]" = WeakKeyDictionary()


# NOTE:
# This synchronous cache client remains intentionally for legacy sync analytics
# code running outside the main HTTP request lifecycle.
@lru_cache(maxsize=1)
def get_regime_cache_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_async_regime_cache_client() -> AsyncRedis:
    settings = get_settings()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    client = _ASYNC_REGIME_CACHE_CLIENTS.get(loop)
    if client is None:
        client = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
        _ASYNC_REGIME_CACHE_CLIENTS[loop] = client
    return client


def _clear_async_regime_cache_clients() -> None:
    _ASYNC_REGIME_CACHE_CLIENTS.clear()


setattr(get_async_regime_cache_client, "cache_clear", _clear_async_regime_cache_clients)


def regime_cache_key(coin_id: int, timeframe: int) -> str:
    return f"{REGIME_CACHE_PREFIX}:{int(coin_id)}:{int(timeframe)}"


def _serialize_regime_payload(*, timeframe: int, regime: str, confidence: float) -> str:
    return json.dumps(
        {
            "timeframe": int(timeframe),
            "regime": regime,
            "confidence": float(confidence),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_regime_payload(raw: str, *, fallback_timeframe: int) -> RegimeRead | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    regime = payload.get("regime")
    if not isinstance(regime, str):
        return None
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return RegimeRead(
        timeframe=int(payload.get("timeframe", fallback_timeframe)),
        regime=regime,
        confidence=confidence,
    )


def cache_regime_snapshot(
    *,
    coin_id: int,
    timeframe: int,
    regime: str,
    confidence: float,
) -> None:
    payload = _serialize_regime_payload(timeframe=timeframe, regime=regime, confidence=confidence)
    get_regime_cache_client().set(
        regime_cache_key(coin_id, timeframe),
        payload,
        ex=REGIME_CACHE_TTL_SECONDS,
    )


async def cache_regime_snapshot_async(
    *,
    coin_id: int,
    timeframe: int,
    regime: str,
    confidence: float,
) -> None:
    payload = _serialize_regime_payload(timeframe=timeframe, regime=regime, confidence=confidence)
    await get_async_regime_cache_client().set(
        regime_cache_key(coin_id, timeframe),
        payload,
        ex=REGIME_CACHE_TTL_SECONDS,
    )


def read_cached_regime(*, coin_id: int, timeframe: int) -> RegimeRead | None:
    raw = get_regime_cache_client().get(regime_cache_key(coin_id, timeframe))
    if raw is None:
        return None
    return _parse_regime_payload(raw, fallback_timeframe=timeframe)


async def read_cached_regime_async(*, coin_id: int, timeframe: int) -> RegimeRead | None:
    raw = await get_async_regime_cache_client().get(regime_cache_key(coin_id, timeframe))
    if raw is None:
        return None
    return _parse_regime_payload(raw, fallback_timeframe=timeframe)
