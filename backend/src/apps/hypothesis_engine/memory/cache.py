import json
from typing import Any

from redis.asyncio import Redis as AsyncRedis

from src.apps.hypothesis_engine.constants import PROMPT_CACHE_PREFIX, PROMPT_CACHE_TTL_SECONDS
from src.core.settings import get_settings


def get_async_ai_cache_client() -> AsyncRedis:
    settings = get_settings()
    return AsyncRedis.from_url(settings.redis_url, decode_responses=True)


def prompt_cache_key(name: str) -> str:
    return f"{PROMPT_CACHE_PREFIX}:{name}:active"


def prompt_version_key(name: str) -> str:
    return f"{PROMPT_CACHE_PREFIX}:{name}:version"


async def read_cached_active_prompt_async(name: str) -> dict[str, Any] | None:
    client = get_async_ai_cache_client()
    try:
        raw = await client.get(prompt_cache_key(name))
        if raw is None:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    finally:
        await client.aclose()


async def cache_active_prompt_async(name: str, payload: dict[str, Any]) -> None:
    client = get_async_ai_cache_client()
    try:
        await client.set(
            prompt_cache_key(name),
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            ex=PROMPT_CACHE_TTL_SECONDS,
        )
    finally:
        await client.aclose()


async def invalidate_prompt_cache_async(name: str) -> None:
    client = get_async_ai_cache_client()
    try:
        await client.delete(prompt_cache_key(name))
        await client.incr(prompt_version_key(name))
    finally:
        await client.aclose()
