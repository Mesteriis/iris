from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import ClassVar

import httpx
import pytest
from iris.apps.market_data import clients, events
from iris.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    RateLimitedMarketSourceError,
    TemporaryMarketSourceError,
)
from iris.apps.market_data.sources.rate_limits import RateLimitPolicy

from tests.factories.market_data import CoinCreateFactory


class DummyMarketSource(BaseMarketSource):
    name = "dummy"
    asset_types: ClassVar[set[str]] = {"crypto"}
    supported_intervals: ClassVar[set[str]] = {"15m"}

    def get_symbol(self, coin) -> str | None:
        return coin.symbol if coin.symbol.startswith("BTC") else None

    async def fetch_bars(self, coin, interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        del coin, interval, start, end
        return []

    def bars_per_request(self, interval: str) -> int:
        del interval
        return 500


def _response(
    *,
    status_code: int = 200,
    payload: object | None = None,
    headers: dict[str, str] | None = None,
    url: str = "https://example.com",
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        headers=headers,
        request=httpx.Request("GET", url),
    )


@pytest.mark.asyncio
async def test_market_source_exports_and_base_methods(monkeypatch) -> None:
    source = DummyMarketSource()
    base_source = BaseMarketSource()
    supported_coin = CoinCreateFactory.build(symbol="BTCUSD_EVT", asset_type="crypto")
    unsupported_coin = CoinCreateFactory.build(symbol="EURUSD_EVT", asset_type="forex")
    start = datetime(2026, 3, 12, 10, 0, tzinfo=UTC)
    end = start + timedelta(minutes=30)

    assert clients.BaseMarketSource is BaseMarketSource
    assert events.publish_candle_events.__name__ == "publish_candle_events"
    assert source.supports_coin(supported_coin, " 15M ")
    assert source.supports_coin(unsupported_coin, "15m") is False
    assert source.supports_coin(supported_coin, "1h") is False
    assert source._limit_for_range("15m", start, end) == 3
    assert source.allows_terminal_gap(supported_coin) is False
    assert source.resolve_provider_symbol("BTCUSD_EVT", fallback="BTCUSDT") == "BTCUSDT"
    assert source.supports_canonical_symbol("BTCUSD_EVT", fallback=True) is True

    aclose_calls: list[str] = []

    async def fake_aclose() -> None:
        aclose_calls.append("closed")

    monkeypatch.setattr(source.client, "aclose", fake_aclose)
    await source.close()
    assert aclose_calls == ["closed"]

    with pytest.raises(NotImplementedError):
        base_source.get_symbol(supported_coin)
    with pytest.raises(NotImplementedError):
        await base_source.fetch_bars(supported_coin, "15m", start, end)
    with pytest.raises(NotImplementedError):
        base_source.bars_per_request("15m")
    await base_source.close()


@pytest.mark.asyncio
async def test_market_source_registry_resolution_helpers(monkeypatch) -> None:
    source = DummyMarketSource()

    class FakeRegistry:
        def resolve_provider_symbol(self, source_name: str, canonical_symbol: str, *, fallback: str | None = None) -> str | None:
            assert source_name == "dummy"
            return "BTC-PROVIDER" if canonical_symbol == "BTCUSD_EVT" else fallback

        def supports_canonical_symbol(self, source_name: str, canonical_symbol: str, *, fallback: bool = False) -> bool:
            assert source_name == "dummy"
            return canonical_symbol == "BTCUSD_EVT" or fallback

    monkeypatch.setattr(
        "iris.apps.market_data.sources.source_capability_registry.get_market_source_capability_registry",
        lambda: FakeRegistry(),
    )

    assert source.resolve_provider_symbol("BTCUSD_EVT", fallback="fallback") == "BTC-PROVIDER"
    assert source.resolve_provider_symbol("ETHUSD_EVT", fallback="fallback") == "fallback"
    assert source.supports_canonical_symbol("BTCUSD_EVT") is True
    assert source.supports_canonical_symbol("ETHUSD_EVT", fallback=False) is False


@pytest.mark.asyncio
async def test_market_source_rate_limit_helpers(monkeypatch) -> None:
    source = DummyMarketSource()
    calls: list[tuple[str, object]] = []

    class FakeRateLimitManager:
        async def is_rate_limited(self, name: str) -> bool:
            calls.append(("is_rate_limited", name))
            return True

        async def set_cooldown(self, name: str, seconds: int) -> None:
            calls.append(("set_cooldown", (name, seconds)))

        async def clear_cooldown(self, name: str) -> None:
            calls.append(("clear_cooldown", name))

    monkeypatch.setattr("iris.apps.market_data.sources.base.get_rate_limit_manager", lambda: FakeRateLimitManager())

    assert await source.is_rate_limited() is True
    await source.set_rate_limit(12)
    await source.clear_rate_limit()

    assert calls == [
        ("is_rate_limited", "dummy"),
        ("set_cooldown", ("dummy", 12)),
        ("clear_cooldown", "dummy"),
    ]


@pytest.mark.asyncio
async def test_market_source_request_success_and_transport_errors(monkeypatch) -> None:
    source = DummyMarketSource()
    response = _response(payload={"ok": True})

    async def fake_rate_limited_get(*args, **kwargs) -> httpx.Response:
        assert args[0] == "dummy"
        assert kwargs["params"] == {"limit": 10}
        assert kwargs["headers"]["X-Test"] == "1"
        assert kwargs["rate_limit_statuses"] == {418}
        assert kwargs["fallback_retry_after_seconds"] == 13
        assert kwargs["cost"] == 2
        return response

    monkeypatch.setattr("iris.apps.market_data.sources.base.rate_limited_get", fake_rate_limited_get)
    assert (
        await source.request(
            "https://example.com/data",
            params={"limit": 10},
            headers={"X-Test": "1"},
            rate_limit_statuses={418},
            fallback_retry_after_seconds=13,
            cost=2,
        )
    ) is response

    async def fake_raise_rate_limit(*args, **kwargs):
        raise RateLimitedMarketSourceError("dummy", 7, "dummy rate limited")

    monkeypatch.setattr("iris.apps.market_data.sources.base.rate_limited_get", fake_raise_rate_limit)
    with pytest.raises(RateLimitedMarketSourceError, match="dummy rate limited"):
        await source.request("https://example.com/data")

    async def fake_raise_http(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("iris.apps.market_data.sources.base.rate_limited_get", fake_raise_http)
    with pytest.raises(TemporaryMarketSourceError, match="dummy transport error"):
        await source.request("https://example.com/data")


@pytest.mark.asyncio
async def test_market_source_uses_proxy_registry_when_direct_bucket_is_limited(monkeypatch) -> None:
    class ProxyDummyMarketSource(DummyMarketSource):
        proxy_pool_mode = "preferred"

    source = ProxyDummyMarketSource()

    class FakeRateLimitManager:
        async def is_rate_limited(self, name: str) -> bool:
            assert name == "dummy"
            return True

    class FakeRegistry:
        async def has_available_proxy(self) -> bool:
            return True

    monkeypatch.setattr("iris.apps.market_data.sources.base.get_rate_limit_manager", lambda: FakeRateLimitManager())
    monkeypatch.setattr("iris.apps.market_data.sources.base.get_free_proxy_registry", lambda: FakeRegistry())

    assert await source.is_rate_limited() is False


@pytest.mark.asyncio
async def test_market_source_request_prefers_proxy_pool(monkeypatch) -> None:
    class ProxyDummyMarketSource(DummyMarketSource):
        proxy_pool_mode = "preferred"

    source = ProxyDummyMarketSource()
    response = _response(payload={"ok": True})
    calls: list[tuple[str, str]] = []

    class FakeRateLimitManager:
        async def cooldown_seconds(self, name: str) -> float:
            assert name == "dummy"
            return 0.0

    class FakeRegistry:
        async def get_best_proxies(self, *, limit: int) -> list[str]:
            assert limit == 2
            return ["http://1.1.1.1:8080", "http://2.2.2.2:8080"]

    async def fake_request_via_proxy(proxy_url: str, *args, **kwargs) -> httpx.Response:
        calls.append(("proxy", proxy_url))
        if proxy_url.endswith("8080") and "1.1.1.1" in proxy_url:
            raise httpx.ConnectError("boom")
        return response

    async def fake_request_direct(*args, **kwargs) -> httpx.Response:
        calls.append(("direct", "used"))
        return response

    monkeypatch.setattr("iris.apps.market_data.sources.base.get_rate_limit_manager", lambda: FakeRateLimitManager())
    monkeypatch.setattr("iris.apps.market_data.sources.base.get_free_proxy_registry", lambda: FakeRegistry())
    monkeypatch.setattr(
        "iris.apps.market_data.sources.base.get_settings",
        lambda: SimpleNamespace(free_proxy_pool_max_proxy_attempts=2),
    )
    monkeypatch.setattr(source, "_request_via_proxy", fake_request_via_proxy)
    monkeypatch.setattr(source, "_request_direct", fake_request_direct)

    result = await source.request("https://example.com/data", headers={"X-Test": "1"})

    assert result is response
    assert calls == [
        ("proxy", "http://1.1.1.1:8080"),
        ("proxy", "http://2.2.2.2:8080"),
    ]


@pytest.mark.asyncio
async def test_market_source_raise_rate_limited_and_retry_after(monkeypatch) -> None:
    source = DummyMarketSource()
    set_calls: list[int] = []

    monkeypatch.setattr(
        "iris.apps.market_data.sources.base.get_rate_limit_policy",
        lambda name: RateLimitPolicy(fallback_retry_after_seconds=9),
    )

    async def fake_set_rate_limit(seconds: int) -> None:
        set_calls.append(seconds)

    monkeypatch.setattr(source, "set_rate_limit", fake_set_rate_limit)

    with pytest.raises(RateLimitedMarketSourceError) as exc_info:
        await source.raise_rate_limited(message="custom message")

    assert exc_info.value.source == "dummy"
    assert exc_info.value.retry_after_seconds == 9
    assert str(exc_info.value) == "custom message"
    assert set_calls == [9]

    with pytest.raises(RateLimitedMarketSourceError) as explicit_info:
        await source.raise_rate_limited(retry_after_seconds=3)
    assert explicit_info.value.retry_after_seconds == 3

    assert BaseMarketSource._retry_after(_response(headers={"Retry-After": "12"}), 5) == 12
    assert BaseMarketSource._retry_after(_response(headers={"gw-ratelimit-reset": "2000"}), 5) == 2
    assert BaseMarketSource._retry_after(_response(headers={"Retry-After": "bad"}), 5) == 5
