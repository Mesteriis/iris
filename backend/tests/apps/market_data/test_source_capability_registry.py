from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from src.apps.market_data.sources import source_capability_registry as registry_module
from src.apps.market_data.sources.source_capability_registry import (
    MarketSourceCapabilityRegistry,
    SourceCapabilitySnapshot,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str) -> None:
        self.values[key] = value


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        eia_api_key="eia",
        fred_api_key="fred",
        polygon_api_key="polygon",
        twelve_data_api_key="twelve",
        alpha_vantage_api_key="alpha",
    )


@pytest.mark.asyncio
async def test_source_capability_registry_refresh_persists_and_resolves(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    registry = MarketSourceCapabilityRegistry()

    async def fake_discover_with_guard(discoverer):
        del discoverer
        return SourceCapabilitySnapshot(
            source_name="binance",
            status="ok",
            discovery_mode="live_listing",
            discovered_at=registry_module.datetime.now(tz=registry_module.UTC),
            provider_symbols=["BTCUSDT"],
            canonical_to_provider={"BTCUSD": "BTCUSDT"},
            provider_to_canonical={"BTCUSDT": "BTCUSD"},
            notes=["fixture"],
        )

    monkeypatch.setattr(registry_module, "get_settings", _settings)
    monkeypatch.setattr(registry_module, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=fake_redis))
    monkeypatch.setattr(registry, "_discover_with_guard", fake_discover_with_guard)

    await registry.start()
    summary = await registry.refresh_once()

    assert summary["status"] == "ok"
    assert summary["sources"]["binance"]["mapped_symbols"] == 1
    assert registry.resolve_provider_symbol("binance", "BTCUSD") == "BTCUSDT"
    assert registry.supports_canonical_symbol("binance", "BTCUSD") is True
    assert "binance" in json.loads(fake_redis.values[registry_module.REDIS_KEY])["sources"]


@pytest.mark.asyncio
async def test_source_capability_registry_loads_existing_redis_payload(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    fake_redis.values[registry_module.REDIS_KEY] = json.dumps(
        {
            "updated_at": "2026-03-16T12:00:00+00:00",
            "sources": {
                "yahoo": {
                    "status": "ok",
                    "discovery_mode": "validated_aliases",
                    "discovered_at": "2026-03-16T12:00:00+00:00",
                    "provider_symbols": ["BTC-USD"],
                    "canonical_to_provider": {"BTCUSD": "BTC-USD"},
                    "provider_to_canonical": {"BTC-USD": "BTCUSD"},
                    "notes": ["fixture"],
                    "error": None,
                }
            },
        }
    )
    monkeypatch.setattr(registry_module, "get_settings", _settings)
    monkeypatch.setattr(registry_module, "get_async_lock_redis", lambda: __import__("asyncio").sleep(0, result=fake_redis))

    registry = MarketSourceCapabilityRegistry()
    await registry.start()

    assert registry.resolve_provider_symbol("yahoo", "BTCUSD") == "BTC-USD"
    assert registry.supports_canonical_symbol("yahoo", "BTCUSD") is True
