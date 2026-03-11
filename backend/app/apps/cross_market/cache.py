from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from redis import Redis

from app.core.settings import get_settings
from app.apps.market_data.domain import ensure_utc

CORRELATION_CACHE_PREFIX = "iris:correlation"
CORRELATION_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7


@dataclass(slots=True, frozen=True)
class CorrelationCacheEntry:
    leader_coin_id: int
    follower_coin_id: int
    correlation: float
    lag_hours: int
    confidence: float
    updated_at: datetime | None


@lru_cache(maxsize=1)
def get_correlation_cache_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def correlation_cache_key(leader_coin_id: int, follower_coin_id: int) -> str:
    return f"{CORRELATION_CACHE_PREFIX}:{int(leader_coin_id)}:{int(follower_coin_id)}"


def cache_correlation_snapshot(
    *,
    leader_coin_id: int,
    follower_coin_id: int,
    correlation: float,
    lag_hours: int,
    confidence: float,
    updated_at: datetime | None,
) -> None:
    payload = json.dumps(
        {
            "leader_coin_id": int(leader_coin_id),
            "follower_coin_id": int(follower_coin_id),
            "correlation": float(correlation),
            "lag_hours": int(lag_hours),
            "confidence": float(confidence),
            "updated_at": ensure_utc(updated_at).isoformat() if updated_at is not None else None,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    get_correlation_cache_client().set(
        correlation_cache_key(leader_coin_id, follower_coin_id),
        payload,
        ex=CORRELATION_CACHE_TTL_SECONDS,
    )


def read_cached_correlation(*, leader_coin_id: int, follower_coin_id: int) -> CorrelationCacheEntry | None:
    raw = get_correlation_cache_client().get(correlation_cache_key(leader_coin_id, follower_coin_id))
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    updated_at_raw = payload.get("updated_at")
    updated_at: datetime | None = None
    if isinstance(updated_at_raw, str):
        try:
            updated_at = ensure_utc(datetime.fromisoformat(updated_at_raw))
        except ValueError:
            updated_at = None
    return CorrelationCacheEntry(
        leader_coin_id=int(payload.get("leader_coin_id", leader_coin_id)),
        follower_coin_id=int(payload.get("follower_coin_id", follower_coin_id)),
        correlation=float(payload.get("correlation", 0.0)),
        lag_hours=int(payload.get("lag_hours", 0)),
        confidence=float(payload.get("confidence", 0.0)),
        updated_at=updated_at,
    )
