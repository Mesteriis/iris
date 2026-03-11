from __future__ import annotations

import json
from functools import lru_cache

from redis import Redis

from app.core.config import get_settings
from app.patterns.regime import RegimeRead

REGIME_CACHE_PREFIX = "iris:regime"
REGIME_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7


@lru_cache(maxsize=1)
def get_regime_cache_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def regime_cache_key(coin_id: int, timeframe: int) -> str:
    return f"{REGIME_CACHE_PREFIX}:{int(coin_id)}:{int(timeframe)}"


def cache_regime_snapshot(
    *,
    coin_id: int,
    timeframe: int,
    regime: str,
    confidence: float,
) -> None:
    payload = json.dumps(
        {
            "timeframe": int(timeframe),
            "regime": regime,
            "confidence": float(confidence),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    get_regime_cache_client().set(
        regime_cache_key(coin_id, timeframe),
        payload,
        ex=REGIME_CACHE_TTL_SECONDS,
    )


def read_cached_regime(*, coin_id: int, timeframe: int) -> RegimeRead | None:
    raw = get_regime_cache_client().get(regime_cache_key(coin_id, timeframe))
    if raw is None:
        return None
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
        timeframe=int(payload.get("timeframe", timeframe)),
        regime=regime,
        confidence=confidence,
    )
