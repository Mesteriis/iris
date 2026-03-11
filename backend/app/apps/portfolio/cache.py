from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from redis import Redis

from app.core.settings import get_settings

PORTFOLIO_STATE_CACHE_KEY = "iris:portfolio:state"
PORTFOLIO_BALANCES_CACHE_KEY = "iris:portfolio:balances"
PORTFOLIO_CACHE_TTL_SECONDS = 60 * 60 * 24


@lru_cache(maxsize=1)
def get_portfolio_cache_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def cache_portfolio_state(payload: dict[str, Any]) -> None:
    get_portfolio_cache_client().set(
        PORTFOLIO_STATE_CACHE_KEY,
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        ex=PORTFOLIO_CACHE_TTL_SECONDS,
    )


def read_cached_portfolio_state() -> dict[str, Any] | None:
    raw = get_portfolio_cache_client().get(PORTFOLIO_STATE_CACHE_KEY)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def cache_portfolio_balances(payload: list[dict[str, Any]]) -> None:
    get_portfolio_cache_client().set(
        PORTFOLIO_BALANCES_CACHE_KEY,
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        ex=PORTFOLIO_CACHE_TTL_SECONDS,
    )


def read_cached_portfolio_balances() -> list[dict[str, Any]] | None:
    raw = get_portfolio_cache_client().get(PORTFOLIO_BALANCES_CACHE_KEY)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, list) else None
