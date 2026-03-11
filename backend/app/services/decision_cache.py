from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from redis import Redis

from app.core.config import get_settings
from app.services.market_data import ensure_utc

DECISION_CACHE_PREFIX = "iris:decision"
DECISION_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7


@dataclass(slots=True, frozen=True)
class DecisionCacheEntry:
    coin_id: int
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None
    created_at: datetime | None


@lru_cache(maxsize=1)
def get_decision_cache_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def decision_cache_key(coin_id: int, timeframe: int) -> str:
    return f"{DECISION_CACHE_PREFIX}:{int(coin_id)}:{int(timeframe)}"


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
    payload = json.dumps(
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
    get_decision_cache_client().set(
        decision_cache_key(coin_id, timeframe),
        payload,
        ex=DECISION_CACHE_TTL_SECONDS,
    )


def read_cached_market_decision(*, coin_id: int, timeframe: int) -> DecisionCacheEntry | None:
    raw = get_decision_cache_client().get(decision_cache_key(coin_id, timeframe))
    if raw is None:
        return None
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
        coin_id=int(payload.get("coin_id", coin_id)),
        timeframe=int(payload.get("timeframe", timeframe)),
        decision=decision,
        confidence=confidence,
        signal_count=signal_count,
        regime=regime,
        created_at=created_at,
    )
