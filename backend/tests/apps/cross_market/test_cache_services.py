from __future__ import annotations

import asyncio
import json

import src.apps.cross_market.cache as correlation_cache_module
import src.apps.cross_market.services as cross_market_services_module
from src.apps.cross_market.cache import (
    CORRELATION_CACHE_TTL_SECONDS,
    _parse_correlation_payload,
    cache_correlation_snapshot,
    cache_correlation_snapshot_async,
    correlation_cache_key,
    get_async_correlation_cache_client,
    get_correlation_cache_client,
    read_cached_correlation,
    read_cached_correlation_async,
)


class _SyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.last_ex: int | None = None

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value
        self.last_ex = ex

    def get(self, key: str) -> str | None:
        return self.storage.get(key)


class _AsyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.last_ex: int | None = None

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value
        self.last_ex = ex

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)


def test_cross_market_cache_round_trip_and_service_exports(monkeypatch, settings, seeded_api_state) -> None:
    sync_client = _SyncCacheClient()
    async_client = _AsyncCacheClient()
    timestamp = seeded_api_state["signal_timestamp"]

    get_correlation_cache_client.cache_clear()
    get_async_correlation_cache_client.cache_clear()
    monkeypatch.setattr(
        correlation_cache_module.Redis, "from_url", staticmethod(lambda url, decode_responses: (url, decode_responses))
    )
    monkeypatch.setattr(
        correlation_cache_module.AsyncRedis,
        "from_url",
        staticmethod(lambda url, decode_responses: (url, decode_responses)),
    )
    assert get_correlation_cache_client() == (settings.redis_url, True)
    assert get_async_correlation_cache_client() == (settings.redis_url, True)
    get_correlation_cache_client.cache_clear()
    get_async_correlation_cache_client.cache_clear()

    monkeypatch.setattr(correlation_cache_module, "get_correlation_cache_client", lambda: sync_client)
    monkeypatch.setattr(correlation_cache_module, "get_async_correlation_cache_client", lambda: async_client)

    cache_correlation_snapshot(
        leader_coin_id=1,
        follower_coin_id=2,
        correlation=0.84,
        lag_hours=4,
        confidence=0.79,
        updated_at=timestamp,
    )
    assert sync_client.last_ex == CORRELATION_CACHE_TTL_SECONDS
    sync_entry = read_cached_correlation(leader_coin_id=1, follower_coin_id=2)
    assert sync_entry is not None
    assert sync_entry.correlation == 0.84
    assert sync_entry.updated_at == timestamp
    assert read_cached_correlation(leader_coin_id=7, follower_coin_id=8) is None

    async def _async_checks() -> None:
        await cache_correlation_snapshot_async(
            leader_coin_id=3,
            follower_coin_id=4,
            correlation=0.72,
            lag_hours=12,
            confidence=0.63,
            updated_at=timestamp,
        )
        assert async_client.last_ex == CORRELATION_CACHE_TTL_SECONDS
        async_entry = await read_cached_correlation_async(leader_coin_id=3, follower_coin_id=4)
        assert async_entry is not None
        assert async_entry.lag_hours == 12
        assert await read_cached_correlation_async(leader_coin_id=9, follower_coin_id=10) is None

    asyncio.run(_async_checks())

    assert _parse_correlation_payload("{", fallback_leader_coin_id=1, fallback_follower_coin_id=2) is None
    parsed = _parse_correlation_payload(
        json.dumps({"confidence": 0.44, "updated_at": "bad-date"}),
        fallback_leader_coin_id=11,
        fallback_follower_coin_id=12,
    )
    assert parsed is not None
    assert parsed.leader_coin_id == 11
    assert parsed.follower_coin_id == 12
    assert parsed.updated_at is None
    parsed_without_timestamp = _parse_correlation_payload(
        json.dumps({"confidence": 0.51, "updated_at": 123}),
        fallback_leader_coin_id=13,
        fallback_follower_coin_id=14,
    )
    assert parsed_without_timestamp is not None
    assert parsed_without_timestamp.updated_at is None
    assert correlation_cache_key(1, 2) == "iris:correlation:1:2"

    assert cross_market_services_module.cache_correlation_snapshot is cache_correlation_snapshot
    assert cross_market_services_module.cache_correlation_snapshot_async is cache_correlation_snapshot_async
    assert cross_market_services_module.read_cached_correlation is read_cached_correlation
    assert cross_market_services_module.read_cached_correlation_async is read_cached_correlation_async
    assert "CrossMarketService" in cross_market_services_module.__all__
    assert "process_cross_market_event" not in cross_market_services_module.__all__
