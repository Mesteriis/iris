import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import cast
from weakref import WeakKeyDictionary

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from iris.apps.market_data.domain import ensure_utc
from iris.core.settings import get_settings

DECISION_CACHE_PREFIX = "iris:decision"
DECISION_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7
_ASYNC_DECISION_CACHE_CLIENTS: WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncRedis] = WeakKeyDictionary()


# NOTE:
# This synchronous cache client remains intentionally for legacy sync analytics
# code running outside the main HTTP request lifecycle.
@dataclass(slots=True, frozen=True)
class DecisionCacheEntry:
    coin_id: int
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None
    created_at: datetime | None


class _AsyncDecisionCacheClientFactory:
    def __call__(self) -> AsyncRedis:
        settings = get_settings()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return cast(AsyncRedis, AsyncRedis.from_url(settings.redis_url, decode_responses=True))
        client = _ASYNC_DECISION_CACHE_CLIENTS.get(loop)
        if client is None:
            client = cast(AsyncRedis, AsyncRedis.from_url(settings.redis_url, decode_responses=True))
            _ASYNC_DECISION_CACHE_CLIENTS[loop] = client
        return client

    def cache_clear(self) -> None:
        _ASYNC_DECISION_CACHE_CLIENTS.clear()


@lru_cache(maxsize=1)
def get_decision_cache_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


get_async_decision_cache_client = _AsyncDecisionCacheClientFactory()


def decision_cache_key(coin_id: int, timeframe: int) -> str:
    return f"{DECISION_CACHE_PREFIX}:{int(coin_id)}:{int(timeframe)}"


def _serialize_decision_payload(
    *,
    coin_id: int,
    timeframe: int,
    decision: str,
    confidence: float,
    signal_count: int,
    regime: str | None,
    created_at: datetime | None,
) -> str:
    return json.dumps(
        {
            "coin_id": int(coin_id),
            "timeframe": int(timeframe),
            "decision": decision,
            "confidence": float(confidence),
            "signal_count": int(signal_count),
            "regime": regime,
            "created_at": ensure_utc(created_at).isoformat() if created_at is not None else None,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_decision_payload(raw: str, *, fallback_coin_id: int, fallback_timeframe: int) -> DecisionCacheEntry | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    decision = payload.get("decision")
    if not isinstance(decision, str):
        return None
    created_at_raw = payload.get("created_at")
    created_at: datetime | None = None
    if isinstance(created_at_raw, str):
        try:
            created_at = ensure_utc(datetime.fromisoformat(created_at_raw))
        except ValueError:
            created_at = None
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    try:
        signal_count = int(payload.get("signal_count", 0))
    except (TypeError, ValueError):
        signal_count = 0
    regime = payload.get("regime")
    if regime is not None and not isinstance(regime, str):
        regime = None
    return DecisionCacheEntry(
        coin_id=int(payload.get("coin_id", fallback_coin_id)),
        timeframe=int(payload.get("timeframe", fallback_timeframe)),
        decision=decision,
        confidence=confidence,
        signal_count=signal_count,
        regime=regime,
        created_at=created_at,
    )


def cache_market_decision_snapshot(
    *,
    coin_id: int,
    timeframe: int,
    decision: str,
    confidence: float,
    signal_count: int,
    regime: str | None,
    created_at: datetime | None,
) -> None:
    payload = _serialize_decision_payload(
        coin_id=coin_id,
        timeframe=timeframe,
        decision=decision,
        confidence=confidence,
        signal_count=signal_count,
        regime=regime,
        created_at=created_at,
    )
    get_decision_cache_client().set(
        decision_cache_key(coin_id, timeframe),
        payload,
        ex=DECISION_CACHE_TTL_SECONDS,
    )


async def cache_market_decision_snapshot_async(
    *,
    coin_id: int,
    timeframe: int,
    decision: str,
    confidence: float,
    signal_count: int,
    regime: str | None,
    created_at: datetime | None,
) -> None:
    payload = _serialize_decision_payload(
        coin_id=coin_id,
        timeframe=timeframe,
        decision=decision,
        confidence=confidence,
        signal_count=signal_count,
        regime=regime,
        created_at=created_at,
    )
    await get_async_decision_cache_client().set(
        decision_cache_key(coin_id, timeframe),
        payload,
        ex=DECISION_CACHE_TTL_SECONDS,
    )


def read_cached_market_decision(*, coin_id: int, timeframe: int) -> DecisionCacheEntry | None:
    raw = get_decision_cache_client().get(decision_cache_key(coin_id, timeframe))
    if not isinstance(raw, str):
        return None
    return _parse_decision_payload(raw, fallback_coin_id=coin_id, fallback_timeframe=timeframe)


async def read_cached_market_decision_async(*, coin_id: int, timeframe: int) -> DecisionCacheEntry | None:
    raw = await get_async_decision_cache_client().get(decision_cache_key(coin_id, timeframe))
    if not isinstance(raw, str):
        return None
    return _parse_decision_payload(raw, fallback_coin_id=coin_id, fallback_timeframe=timeframe)
