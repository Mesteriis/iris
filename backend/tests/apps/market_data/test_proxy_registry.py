from datetime import timedelta
from types import SimpleNamespace

import pytest
from src.apps.market_data.domain import utc_now
from src.apps.market_data.sources import proxy_registry as proxy_registry_module
from src.apps.market_data.sources.proxy_registry import FreeProxyRegistry, ProxyRecord


def _settings(tmp_path, **overrides):
    values = {
        "runtime_data_dir": str(tmp_path),
        "free_proxy_pool_enabled": True,
        "free_proxy_pool_source_urls": ["https://example.com/http.txt", "https://example.com/http.json"],
        "free_proxy_pool_probe_urls": ["https://finance.yahoo.com/robots.txt"],
        "free_proxy_pool_refresh_interval_seconds": 1800,
        "free_proxy_pool_validation_batch_size": 16,
        "free_proxy_pool_max_entries": 32,
        "free_proxy_pool_request_timeout_seconds": 5.0,
        "free_proxy_pool_persist_interval_seconds": 300,
        "free_proxy_pool_max_proxy_attempts": 3,
        "free_proxy_pool_min_rating": 0.2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_proxy_registry_refresh_imports_normalizes_and_probes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(proxy_registry_module, "get_settings", lambda: _settings(tmp_path))
    registry = FreeProxyRegistry()
    probed: list[str] = []

    async def fake_fetch_proxy_candidates() -> set[tuple[str, str]]:
        return {
            ("http://1.1.1.1:80", "https://example.com/http.txt"),
            ("http://2.2.2.2:80", "https://example.com/http.json"),
        }

    async def fake_probe_proxy(proxy_url: str) -> None:
        probed.append(proxy_url)
        await registry.record_success(proxy_url, latency_ms=90.0 if "1.1.1.1" in proxy_url else 150.0)

    monkeypatch.setattr(registry, "_fetch_proxy_candidates", fake_fetch_proxy_candidates)
    monkeypatch.setattr(registry, "_probe_proxy", fake_probe_proxy)

    await registry.refresh_once()

    assert set(probed) == {"http://1.1.1.1:80", "http://2.2.2.2:80"}
    assert set(await registry.get_best_proxies(limit=2, min_rating=0.0)) == {"http://1.1.1.1:80", "http://2.2.2.2:80"}
    assert registry._records["http://1.1.1.1:80"].source_urls == ["https://example.com/http.txt"]
    assert registry._records["http://2.2.2.2:80"].source_urls == ["https://example.com/http.json"]


@pytest.mark.asyncio
async def test_proxy_registry_persists_and_reloads_records(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(proxy_registry_module, "get_settings", lambda: _settings(tmp_path, free_proxy_pool_enabled=False))
    registry = FreeProxyRegistry()
    registry._records["http://3.3.3.3:8080"] = ProxyRecord(
        proxy_url="http://3.3.3.3:8080",
        source_urls=["https://example.com/http.txt"],
        imported_at=utc_now(),
        rating=0.77,
    )
    await registry.record_success("http://3.3.3.3:8080", latency_ms=120.0)
    await registry._persist_to_disk()

    restored = FreeProxyRegistry()
    await restored._load_from_disk()

    record = restored._records["http://3.3.3.3:8080"]
    assert record.rating > 0.0
    assert record.success_count == 1
    assert record.average_latency_ms == 120.0


def test_proxy_registry_parses_multiple_payload_shapes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(proxy_registry_module, "get_settings", lambda: _settings(tmp_path))
    registry = FreeProxyRegistry()

    parsed = registry._parse_proxy_payload(
        [
            "4.4.4.4:8080",
            {"proxy": "http://5.5.5.5:3128"},
            {"url": "https://6.6.6.6:443"},
            {"ip": "7.7.7.7", "port": 8000},
            {"ignored": "value"},
        ]
    )

    assert parsed == {
        "http://4.4.4.4:8080",
        "http://5.5.5.5:3128",
        "https://6.6.6.6:443",
        "http://7.7.7.7:8000",
    }


@pytest.mark.asyncio
async def test_proxy_registry_respects_cooldown_and_prunes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(proxy_registry_module, "get_settings", lambda: _settings(tmp_path, free_proxy_pool_max_entries=2))
    registry = FreeProxyRegistry()
    now = utc_now()
    registry._records = {
        "http://1.1.1.1:80": ProxyRecord(proxy_url="http://1.1.1.1:80", rating=0.95, imported_at=now),
        "http://2.2.2.2:80": ProxyRecord(proxy_url="http://2.2.2.2:80", rating=0.55, imported_at=now),
        "http://3.3.3.3:80": ProxyRecord(
            proxy_url="http://3.3.3.3:80",
            rating=0.85,
            imported_at=now,
            cooldown_until=now + timedelta(minutes=10),
        ),
    }

    async with registry._lock:
        registry._prune_records_locked()

    assert set(registry._records) == {"http://1.1.1.1:80", "http://2.2.2.2:80"}
    assert await registry.has_available_proxy(min_rating=0.8) is True
    assert await registry.get_best_proxies(limit=2, min_rating=0.8) == ["http://1.1.1.1:80"]
