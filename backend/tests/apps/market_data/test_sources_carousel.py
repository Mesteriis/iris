from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.apps.market_data import sources as carousel_module
from app.apps.market_data.sources import MarketFetchResult, MarketSourceCarousel, get_market_source_carousel
from app.apps.market_data.sources.base import (
    MarketBar,
    MarketSourceError,
    RateLimitedMarketSourceError,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)
from tests.factories.market_data import CoinCreateFactory


class FakeSource:
    def __init__(
        self,
        name: str,
        *,
        supports: bool = True,
        rate_limited: bool = False,
        bars_per_request: int = 2,
        allows_terminal_gap: bool = False,
        results: list[object] | None = None,
    ) -> None:
        self.name = name
        self._supports = supports
        self._rate_limited = rate_limited
        self._bars_per_request = bars_per_request
        self._allows_terminal_gap = allows_terminal_gap
        self._results = list(results or [])
        self.clear_calls = 0
        self.close_calls = 0
        self.fetch_calls: list[tuple[datetime, datetime]] = []

    async def close(self) -> None:
        self.close_calls += 1

    def supports_coin(self, coin, interval: str) -> bool:
        del coin, interval
        return self._supports

    async def is_rate_limited(self) -> bool:
        return self._rate_limited

    async def clear_rate_limit(self) -> None:
        self.clear_calls += 1

    def bars_per_request(self, interval: str) -> int:
        del interval
        return self._bars_per_request

    def allows_terminal_gap(self, coin) -> bool:
        del coin
        return self._allows_terminal_gap

    async def fetch_bars(self, coin, interval: str, start: datetime, end: datetime):
        del coin, interval
        self.fetch_calls.append((start, end))
        if not self._results:
            return []
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _coin(*, symbol: str = "BTCUSD_EVT", asset_type: str = "crypto", source: str = "default"):
    return CoinCreateFactory.build(symbol=symbol, asset_type=asset_type, source=source)


def _bars(start: datetime, count: int, *, interval_minutes: int = 15, source: str = "fixture") -> list[MarketBar]:
    values: list[MarketBar] = []
    for index in range(count):
        timestamp = start + timedelta(minutes=interval_minutes * index)
        price = 100.0 + index
        values.append(
            MarketBar(
                timestamp=timestamp,
                open=price,
                high=price + 1.0,
                low=price - 1.0,
                close=price + 0.5,
                volume=10.0 + index,
                source=source,
            )
        )
    return values


@pytest.mark.asyncio
async def test_market_source_carousel_provider_order_close_and_singleton() -> None:
    carousel = MarketSourceCarousel()
    coin_sets = [
        (_coin(asset_type="crypto"), ["binance", "kucoin", "kraken", "coinbase", "yahoo"]),
        (_coin(symbol="DJI", asset_type="index"), ["moex", "polygon", "twelvedata", "yahoo"]),
        (_coin(symbol="EURUSD", asset_type="forex"), ["polygon", "twelvedata", "alphavantage", "yahoo"]),
        (_coin(symbol="XAUUSD", asset_type="metal"), ["twelvedata", "yahoo"]),
        (_coin(symbol="WTIUSD", asset_type="energy"), ["yahoo"]),
        (_coin(asset_type="crypto", source="coinbase"), ["coinbase", "binance", "kucoin", "kraken", "yahoo"]),
    ]

    for coin, expected in coin_sets:
        assert carousel.provider_names_for_coin(coin) == expected

    fake_a = FakeSource("a")
    fake_b = FakeSource("b")
    carousel.sources = {"a": fake_a, "b": fake_b}
    await carousel.close()
    assert fake_a.close_calls == 1
    assert fake_b.close_calls == 1

    carousel_module._carousel = None
    first = get_market_source_carousel()
    second = get_market_source_carousel()
    assert first is second
    await first.close()
    carousel_module._carousel = None


@pytest.mark.asyncio
async def test_market_source_carousel_handles_no_supported_provider() -> None:
    carousel = MarketSourceCarousel()
    carousel.sources = {"only": FakeSource("only", supports=False)}
    coin = _coin()
    carousel.provider_names_for_coin = lambda coin: ["only"]  # type: ignore[method-assign]

    result = await carousel.fetch_history_window(
        coin,
        "15m",
        datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 3, 12, 10, 30, tzinfo=timezone.utc),
    )

    assert result == MarketFetchResult(
        bars=[],
        completed=False,
        source_names=[],
        error="No market source supports BTCUSD_EVT with interval 15m.",
    )


@pytest.mark.asyncio
async def test_market_source_carousel_success_and_cursor_rotation(monkeypatch) -> None:
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)
    first_source = FakeSource("first", results=[_bars(start, 3, source="first")], bars_per_request=3)
    second_source = FakeSource("second", results=[_bars(start, 3, source="second")], bars_per_request=3)
    carousel = MarketSourceCarousel()
    carousel.sources = {"first": first_source, "second": second_source}
    coin = _coin()
    monkeypatch.setattr(carousel, "provider_names_for_coin", lambda coin: ["first", "second"])

    first_result = await carousel.fetch_history_window(coin, "15m", start, end)
    second_result = await carousel.fetch_history_window(coin, "15m", start, end)

    assert first_result.completed is True
    assert [bar.source for bar in first_result.bars] == ["first", "first", "first"]
    assert second_result.completed is True
    assert [bar.source for bar in second_result.bars] == ["second", "second", "second"]
    assert carousel._cursor[(coin.symbol, "15m")] == 0
    assert first_source.clear_calls == 1
    assert second_source.clear_calls == 1


@pytest.mark.asyncio
async def test_market_source_carousel_skips_rate_limited_and_provider_errors(monkeypatch) -> None:
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)
    bars = _bars(start, 3, source="success")
    carousel = MarketSourceCarousel()
    carousel.sources = {
        "limited": FakeSource("limited", rate_limited=True),
        "rl_error": FakeSource("rl_error", results=[RateLimitedMarketSourceError("rl_error", 4, "rl hit")]),
        "unsupported": FakeSource("unsupported", results=[UnsupportedMarketSourceQuery("unsupported query")]),
        "temporary": FakeSource("temporary", results=[TemporaryMarketSourceError("temporary error")]),
        "generic": FakeSource("generic", results=[MarketSourceError("generic error")]),
        "success": FakeSource("success", results=[bars], bars_per_request=3),
    }
    monkeypatch.setattr(
        carousel,
        "provider_names_for_coin",
        lambda coin: ["limited", "rl_error", "unsupported", "temporary", "generic", "success"],
    )

    result = await carousel.fetch_history_window(_coin(), "15m", start, end)

    assert result.completed is True
    assert [bar.source for bar in result.bars] == ["success", "success", "success"]
    assert result.source_names == ["limited", "rl_error", "unsupported", "temporary", "generic", "success"]


@pytest.mark.asyncio
async def test_market_source_carousel_allows_terminal_gap(monkeypatch) -> None:
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)
    source = FakeSource(
        "yahoo",
        results=[_bars(start, 2, source="yahoo"), []],
        bars_per_request=2,
        allows_terminal_gap=True,
    )
    carousel = MarketSourceCarousel()
    carousel.sources = {"yahoo": source}
    monkeypatch.setattr(carousel, "provider_names_for_coin", lambda coin: ["yahoo"])

    result = await carousel.fetch_history_window(_coin(asset_type="index"), "15m", start, end)

    assert result.completed is True
    assert [bar.timestamp for bar in result.bars] == [start, start + timedelta(minutes=15)]
    assert result.error is None


@pytest.mark.asyncio
async def test_market_source_carousel_exhausts_when_sources_do_not_advance(monkeypatch) -> None:
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)
    stale_bar = _bars(start - timedelta(minutes=15), 1, source="stale")
    source = FakeSource("stale", results=[stale_bar, stale_bar, stale_bar], bars_per_request=2)
    carousel = MarketSourceCarousel()
    carousel.sources = {"stale": source}
    monkeypatch.setattr(carousel, "provider_names_for_coin", lambda coin: ["stale"])

    result = await carousel.fetch_history_window(_coin(), "15m", start, end)

    assert result.completed is False
    assert result.bars == []
    assert result.error == "stale did not advance cursor for BTCUSD_EVT."


@pytest.mark.asyncio
async def test_market_source_carousel_exhausts_on_empty_provider_windows(monkeypatch) -> None:
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)
    source = FakeSource("empty", results=[[], [], []], bars_per_request=2)
    carousel = MarketSourceCarousel()
    carousel.sources = {"empty": source}
    monkeypatch.setattr(carousel, "provider_names_for_coin", lambda coin: ["empty"])

    result = await carousel.fetch_history_window(_coin(), "15m", start, end)

    assert result.completed is False
    assert result.error == "empty returned no bars for BTCUSD_EVT."
