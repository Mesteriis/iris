from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.apps.market_data.sources.alphavantage import AlphaVantageForexMarketSource
from src.apps.market_data.sources.base import RateLimitedMarketSourceError, TemporaryMarketSourceError, UnsupportedMarketSourceQuery
from src.apps.market_data.sources.binance import BinanceMarketSource
from src.apps.market_data.sources.coinbase import CoinbaseMarketSource
from src.apps.market_data.sources.kraken import KrakenMarketSource
from src.apps.market_data.sources.kucoin import KucoinMarketSource
from src.apps.market_data.sources.moex import MOEX_PAGE_SIZE, MoexIndexMarketSource
from src.apps.market_data.sources.polygon import PolygonMarketSource
from src.apps.market_data.sources.twelvedata import TwelveDataMarketSource
from src.apps.market_data.sources.yfinance import YahooMarketSource
from tests.factories.base import fake
from tests.factories.market_data import CoinCreateFactory


def _coin(*, symbol: str, asset_type: str, source: str = "default"):
    return CoinCreateFactory.build(symbol=symbol, asset_type=asset_type, source=source)


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
async def test_binance_market_source_parses_payload_and_errors(monkeypatch) -> None:
    source = BinanceMarketSource()
    coin = _coin(symbol="BTCUSD", asset_type="crypto")
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)

    assert source.get_symbol(coin) == "BTCUSDT"
    assert source.bars_per_request("15m") == 1000

    async def success_request(url: str, **kwargs):
        assert url == source.base_url
        assert kwargs["params"]["symbol"] == "BTCUSDT"
        return _response(
            payload=[
                [int((start + timedelta(minutes=15)).timestamp() * 1000), "101", "103", "100", "102", "11"],
                [int(start.timestamp() * 1000), "100", "102", "99", "101", "10"],
            ]
        )

    monkeypatch.setattr(source, "request", success_request)
    bars = await source.fetch_bars(coin, "15m", start, end)
    assert [bar.timestamp for bar in bars] == [start, start + timedelta(minutes=15)]
    assert bars[0].volume == 10.0

    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(_coin(symbol="XRPUSD", asset_type="crypto"), "15m", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=400)))
    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(coin, "15m", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=500)))
    with pytest.raises(TemporaryMarketSourceError, match="binance http error: 500"):
        await source.fetch_bars(coin, "15m", start, end)


@pytest.mark.asyncio
async def test_coinbase_market_source_parses_payload_and_errors(monkeypatch) -> None:
    source = CoinbaseMarketSource()
    coin = _coin(symbol="BTCUSD", asset_type="crypto")
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)

    assert source.get_symbol(coin) == "BTC-USD"
    assert source.bars_per_request("15m") == 300

    async def success_request(url: str, **kwargs):
        assert url.endswith("/BTC-USD/candles")
        assert kwargs["params"]["granularity"] == 900
        return _response(
            payload=[
                [int((start + timedelta(minutes=15)).timestamp()), 99, 103, 100, 102, 12],
                [int(start.timestamp()), 98, 102, 99, 101, 11],
            ]
        )

    monkeypatch.setattr(source, "request", success_request)
    bars = await source.fetch_bars(coin, "15m", start, end)
    assert [bar.close for bar in bars] == [101.0, 102.0]

    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(_coin(symbol="RENDERUSD", asset_type="crypto"), "15m", start, end)
    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(coin, "4h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=404)))
    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(coin, "15m", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=500)))
    with pytest.raises(TemporaryMarketSourceError, match="coinbase http error: 500"):
        await source.fetch_bars(coin, "15m", start, end)


@pytest.mark.asyncio
async def test_kraken_market_source_parses_payload_and_errors(monkeypatch) -> None:
    source = KrakenMarketSource()
    coin = _coin(symbol="BTCUSD", asset_type="crypto")
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    assert source.get_symbol(coin) == "XXBTZUSD"
    assert source.bars_per_request("1h") == 720

    async def success_request(*args, **kwargs):
        return _response(
            payload={
                "error": [],
                "result": {
                    "XXBTZUSD": [
                        [int((start - timedelta(hours=1)).timestamp()), "1", "2", "0.5", "1.5", "0", "10"],
                        [int(start.timestamp()), "2", "3", "1.5", "2.5", "0", "12"],
                        [int(end.timestamp()), "3", "4", "2.5", "3.5", "0", "14"],
                    ],
                    "last": int(end.timestamp()),
                },
            }
        )

    monkeypatch.setattr(source, "request", success_request)
    bars = await source.fetch_bars(coin, "1h", start, end)
    assert [bar.timestamp for bar in bars] == [start, end]

    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(_coin(symbol="DOGEUSD", asset_type="crypto"), "1h", start, end)

    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(coin, "1h", start, start + timedelta(days=100))

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=500)))
    with pytest.raises(TemporaryMarketSourceError, match="kraken http error: 500"):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"error": ["boom"], "result": {}})))
    with pytest.raises(TemporaryMarketSourceError, match="kraken api error"):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"error": [], "result": {"last": 1}})))
    assert await source.fetch_bars(coin, "1h", start, end) == []


@pytest.mark.asyncio
async def test_kucoin_market_source_parses_payload_and_errors(monkeypatch) -> None:
    source = KucoinMarketSource()
    coin = _coin(symbol="BTCUSD", asset_type="crypto")
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)

    assert source.get_symbol(coin) == "BTC-USDT"
    assert source.bars_per_request("15m") == 500

    async def success_request(url: str, **kwargs):
        assert kwargs["params"]["type"] == "15min"
        return _response(
            payload={
                "code": "200000",
                "data": [
                    [int((start + timedelta(minutes=15)).timestamp()), "101", "102", "103", "100", "11"],
                    [int(start.timestamp()), "100", "101", "102", "99", "10"],
                ],
            }
        )

    monkeypatch.setattr(source, "request", success_request)
    bars = await source.fetch_bars(coin, "15m", start, end)
    assert [bar.open for bar in bars] == [100.0, 101.0]

    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(_coin(symbol="EURUSD", asset_type="forex"), "15m", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=404)))
    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(coin, "15m", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=500)))
    with pytest.raises(TemporaryMarketSourceError, match="kucoin http error: 500"):
        await source.fetch_bars(coin, "15m", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"code": "400100", "msg": "bad"})))
    with pytest.raises(TemporaryMarketSourceError, match="kucoin api error: bad"):
        await source.fetch_bars(coin, "15m", start, end)


@pytest.mark.asyncio
async def test_polygon_market_source_supports_parses_and_resamples(monkeypatch) -> None:
    source = PolygonMarketSource()
    coin = _coin(symbol="EURUSD", asset_type="forex")
    start = datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=8)

    source.api_key = ""
    assert source.supports_coin(coin, "1h") is False
    source.api_key = "polygon-key"
    assert source.supports_coin(coin, "1h") is True
    assert source.get_symbol(coin) == "C:EURUSD"
    assert source.bars_per_request("1h") == 50_000
    assert source.allows_terminal_gap(coin) is True

    async def success_request(url: str, **kwargs):
        assert url.endswith("/C:EURUSD/range/4/hour/1773302400000/1773331200000")
        assert kwargs["params"]["apiKey"] == "polygon-key"
        return _response(
            payload={
                "status": "ok",
                "results": [
                    {"t": int(start.timestamp() * 1000), "o": 1.1, "h": 1.2, "l": 1.0, "c": 1.15, "v": 100},
                    {"t": int((start + timedelta(hours=4)).timestamp() * 1000), "o": 1.15, "h": 1.25, "l": 1.1, "c": 1.2},
                    {"t": None, "o": 1.0, "h": 1.2, "l": 1.0, "c": 1.1},
                ],
            }
        )

    monkeypatch.setattr(source, "request", success_request)
    resampled = await source.fetch_bars(coin, "4h", start, end)
    assert len(resampled) == 2
    assert resampled[0].volume == 100.0

    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(_coin(symbol="BTCUSD", asset_type="crypto"), "1h", start, end)

    unauthorized = _response(status_code=401, payload={"message": "invalid api key"})
    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=unauthorized))
    with pytest.raises(UnsupportedMarketSourceQuery, match="invalid api key"):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=500)))
    with pytest.raises(TemporaryMarketSourceError, match="polygon http error: 500"):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"status": "error", "message": "unknown api key"})))
    with pytest.raises(UnsupportedMarketSourceQuery, match="unknown api key"):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"status": "error", "message": "temporary outage"})))
    with pytest.raises(TemporaryMarketSourceError, match="temporary outage"):
        await source.fetch_bars(coin, "1h", start, end)

    class BadJsonResponse:
        status_code = 401

        def json(self):
            raise ValueError("bad payload")

        def raise_for_status(self):
            return None

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=BadJsonResponse()))
    with pytest.raises(UnsupportedMarketSourceQuery, match="polygon rejected params"):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=401, payload=["not-a-dict"])))
    with pytest.raises(UnsupportedMarketSourceQuery, match="polygon rejected params"):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(
        source,
        "request",
        lambda *args, **kwargs: __import__("asyncio").sleep(
            0,
            result=_response(
                payload={
                    "status": "delayed",
                    "results": [{"t": int(start.timestamp() * 1000), "o": 1.1, "h": 1.2, "l": 1.0, "c": 1.15, "v": 100}],
                }
            ),
        ),
    )
    assert len(await source.fetch_bars(coin, "1h", start, start + timedelta(hours=1))) == 1


@pytest.mark.asyncio
async def test_twelvedata_market_source_symbol_resolution_and_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.apps.market_data.sources.twelvedata.get_settings",
        lambda: type("Settings", (), {"twelve_data_api_key": "header-key"})(),
    )
    configured_source = TwelveDataMarketSource()
    assert configured_source.client.headers["Authorization"] == "apikey header-key"

    monkeypatch.setattr(
        "src.apps.market_data.sources.twelvedata.get_settings",
        lambda: type("Settings", (), {"twelve_data_api_key": ""})(),
    )
    source = TwelveDataMarketSource()
    coin = _coin(symbol="DJI", asset_type="index")
    start = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    source.api_key = ""
    assert source.supports_coin(coin, "1h") is False
    source.api_key = "twelve-key"
    assert source.supports_coin(coin, "1h") is True
    assert source.get_symbol(coin) == "DJI"
    assert source.get_symbol(_coin(symbol="COPPER", asset_type="metal")) == "COPPER"
    assert source.bars_per_request("1h") == 5000
    assert source.allows_terminal_gap(coin) is True
    assert source._candidate_symbols(coin) == ["DJI", "^DJI"]
    assert source._candidate_symbols(_coin(symbol="XAUUSD", asset_type="metal")) == ["XAU/USD"]
    assert source._candidate_symbols(_coin(symbol="COPPER", asset_type="metal")) == ["COPPER"]

    async def success_request(*args, **kwargs):
        assert kwargs["params"]["symbol"] == "DJI"
        return _response(
            payload={
                "values": [
                    {"datetime": "2026-03-12 11:00:00", "open": "110", "high": "112", "low": "109", "close": "111", "volume": "12"},
                    {"datetime": "2026-03-12 10:00:00", "open": "100", "high": "102", "low": "99", "close": "101"},
                    {"datetime": "2026-03-12 12:00:00", "open": "1", "high": "2", "low": None, "close": "1.5"},
                ]
            }
        )

    monkeypatch.setattr(source, "request", success_request)
    bars = await source._request_symbol("DJI", "1h", start, end)
    assert [bar.timestamp for bar in bars] == [start, end]
    assert bars[0].volume is None

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=500)))
    with pytest.raises(TemporaryMarketSourceError, match="twelvedata http error: 500"):
        await source._request_symbol("DJI", "1h", start, end)

    async def fake_raise_rate_limited(**kwargs):
        raise RateLimitedMarketSourceError("twelvedata", 60, kwargs["message"])

    monkeypatch.setattr(source, "raise_rate_limited", fake_raise_rate_limited)
    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"status": "error", "code": 429, "message": "rate limit"})))
    with pytest.raises(RateLimitedMarketSourceError, match="twelvedata rate limited"):
        await source._request_symbol("DJI", "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"status": "error", "code": 403, "message": "Consider upgrading"})))
    with pytest.raises(UnsupportedMarketSourceQuery, match="Consider upgrading"):
        await source._request_symbol("DJI", "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"status": "error", "code": 401, "message": "bad token"})))
    with pytest.raises(UnsupportedMarketSourceQuery, match="bad token"):
        await source._request_symbol("DJI", "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"status": "error", "code": 500, "message": "temporary"})))
    with pytest.raises(TemporaryMarketSourceError, match="temporary"):
        await source._request_symbol("DJI", "1h", start, end)

    calls: list[str] = []

    async def fake_request_symbol(symbol: str, interval: str, start_at: datetime, end_at: datetime):
        del interval, start_at, end_at
        calls.append(symbol)
        if symbol == "DJI":
            raise UnsupportedMarketSourceQuery("wrong symbol")
        return bars

    monkeypatch.setattr(source, "_request_symbol", fake_request_symbol)
    resolved_bars = await source.fetch_bars(coin, "1h", start, end)
    assert source._resolved_symbols["DJI"] == "^DJI"
    assert source.get_symbol(coin) == "^DJI"
    assert calls == ["DJI", "^DJI"]
    assert resolved_bars == bars

    async def empty_request_symbol(symbol: str, interval: str, start_at: datetime, end_at: datetime):
        del symbol, interval, start_at, end_at
        return []

    source._resolved_symbols.clear()
    monkeypatch.setattr(source, "_request_symbol", empty_request_symbol)
    assert await source.fetch_bars(coin, "1h", start, end) == []
    assert source._resolved_symbols == {}

    source._resolved_symbols.clear()

    async def always_unsupported(*args, **kwargs):
        raise UnsupportedMarketSourceQuery("no data")

    monkeypatch.setattr(source, "_request_symbol", always_unsupported)
    with pytest.raises(UnsupportedMarketSourceQuery, match="no data"):
        await source.fetch_bars(coin, "1h", start, end)


@pytest.mark.asyncio
async def test_yahoo_market_source_parses_payload_and_resamples(monkeypatch) -> None:
    source = YahooMarketSource()
    coin = _coin(symbol="BTCUSD", asset_type="crypto")
    start = datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=8)

    assert source.get_symbol(coin) == "BTC-USD"
    assert source.bars_per_request("1d") >= 2000
    assert source.allows_terminal_gap(coin) is False
    assert source.allows_terminal_gap(_coin(symbol="DJI", asset_type="index")) is True

    async def success_request(url: str, **kwargs):
        assert url.endswith("/BTC-USD")
        assert kwargs["params"]["interval"] == "60m"
        return _response(
            payload={
                "chart": {
                    "result": [
                        {
                                "timestamp": [
                                    int(start.timestamp()),
                                    int((start + timedelta(hours=4)).timestamp()),
                                    int((start + timedelta(hours=4)).timestamp()),
                                ],
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": [100, 101, None],
                                            "high": [102, 103, 105],
                                            "low": [99, 100, 95],
                                            "close": [101, 102, 104],
                                            "volume": [10, None, 12],
                                        }
                                    ]
                                },
                            }
                    ]
                }
            }
        )

    monkeypatch.setattr(source, "request", success_request)
    bars = await source.fetch_bars(coin, "4h", start, end)
    assert len(bars) == 2
    assert bars[0].high == 102.0
    assert bars[1].volume == 0.0

    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(_coin(symbol="EURGBP", asset_type="forex"), "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=404)))
    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=500)))
    with pytest.raises(TemporaryMarketSourceError, match="yahoo http error: 500"):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"chart": {"error": "bad"}})))
    with pytest.raises(TemporaryMarketSourceError, match="yahoo api error"):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"chart": {"result": []}})))
    assert await source.fetch_bars(coin, "1h", start, end) == []

    monkeypatch.setattr(
        source,
        "request",
        lambda *args, **kwargs: __import__("asyncio").sleep(
            0,
            result=_response(
                payload={
                    "chart": {
                        "result": [
                            {
                                "timestamp": [int(start.timestamp())],
                                "indicators": {"quote": [{"open": [100], "high": [101], "low": [99], "close": [100.5], "volume": [7]}]},
                            }
                        ]
                    }
                }
            ),
        ),
    )
    assert len(await source.fetch_bars(coin, "1h", start, start)) == 1


@pytest.mark.asyncio
async def test_alpha_vantage_market_source_parses_payload_and_errors(monkeypatch) -> None:
    source = AlphaVantageForexMarketSource()
    coin = _coin(symbol="EURUSD", asset_type="forex")
    start = datetime(2026, 3, 12, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    source.api_key = ""
    assert source.supports_coin(coin, "1d") is False
    source.api_key = "alpha-key"
    assert source.supports_coin(coin, "1d") is True
    assert source.get_symbol(coin) == "EUR/USD"
    assert source.get_symbol(_coin(symbol="BTCUSD", asset_type="crypto")) is None
    assert source.bars_per_request("1d") == 5000
    assert source.bars_per_request("1h") == 100
    assert source.allows_terminal_gap(coin) is True

    intraday_payload = {
        "Time Series FX (60min)": {
            "2026-03-12 12:00:00": {"1. open": "1.2", "2. high": "1.3", "3. low": "1.1", "4. close": "1.25"},
            "2026-03-12 08:00:00": {"1. open": "1.0", "2. high": "1.1", "3. low": "0.9", "4. close": "1.05"},
            "bad": {"1. open": "1.0", "2. high": "1.1", "3. low": "0.9", "4. close": "1.05"},
            "2026-03-12 06:00:00": [],
        }
    }
    daily_payload = {
        "Time Series FX (Daily)": {
            "2026-03-12": {"1. open": "1.2", "2. high": "1.3", "3. low": "1.1", "4. close": "1.25"},
            "2026-03-10": {"1. open": "1.0", "2. high": "1.1", "3. low": "0.9", "4. close": "1.05"},
            "broken": {"1. open": "1.0"},
            "2026-03-11": [],
        }
    }

    assert source._parse_intraday_payload({}, "1h", start, end) == []
    intraday = source._parse_intraday_payload(intraday_payload, "1h", start, end)
    assert [bar.timestamp.hour for bar in intraday] == [8, 12]

    resampled = source._parse_intraday_payload(intraday_payload, "4h", start, end)
    assert len(resampled) == 2

    assert source._parse_daily_payload({}, start, end) == []
    daily = source._parse_daily_payload(daily_payload, start, end)
    assert len(daily) == 1

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=500)))
    with pytest.raises(TemporaryMarketSourceError, match="alphavantage http error: 500"):
        await source._request_payload({"function": "FX_DAILY"})

    async def fake_raise_rate_limited(**kwargs):
        raise RateLimitedMarketSourceError("alphavantage", 300, kwargs["message"])

    monkeypatch.setattr(source, "raise_rate_limited", fake_raise_rate_limited)
    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"Note": "too many"})))
    with pytest.raises(RateLimitedMarketSourceError, match="alphavantage rate limited"):
        await source._request_payload({"function": "FX_DAILY"})

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"Information": "Premium endpoint"})))
    with pytest.raises(UnsupportedMarketSourceQuery, match="Premium endpoint"):
        await source._request_payload({"function": "FX_DAILY"})

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"Information": "Free API key plan"})))
    with pytest.raises(UnsupportedMarketSourceQuery, match="Free API key plan"):
        await source._request_payload({"function": "FX_DAILY"})

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"Information": "temporary issue"})))
    with pytest.raises(TemporaryMarketSourceError, match="temporary issue"):
        await source._request_payload({"function": "FX_DAILY"})

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"Error Message": "bad pair"})))
    with pytest.raises(UnsupportedMarketSourceQuery, match="bad pair"):
        await source._request_payload({"function": "FX_DAILY"})

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(payload={"ok": True})))
    assert await source._request_payload({"function": "FX_DAILY"}) == {"ok": True}

    monkeypatch.setattr(source, "_request_payload", lambda params: __import__("asyncio").sleep(0, result=daily_payload if params["function"] == "FX_DAILY" else intraday_payload))
    daily_result = await source.fetch_bars(coin, "1d", start, end)
    intraday_result = await source.fetch_bars(coin, "1h", start, end)
    assert len(daily_result) == 1
    assert len(intraday_result) == 2

    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(_coin(symbol="BTCUSD", asset_type="crypto"), "1d", start, end)


@pytest.mark.asyncio
async def test_moex_market_source_paginates_and_resamples(monkeypatch) -> None:
    source = MoexIndexMarketSource()
    coin = _coin(symbol="IMOEX", asset_type="index")
    start = datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=4)

    assert source.get_symbol(coin) == "IMOEX"
    assert source.bars_per_request("1h") == MOEX_PAGE_SIZE
    assert source.allows_terminal_gap(coin) is True

    page_one = [
        [100.0, 101.0, 102.0, 99.0, 0, 10.0, start.isoformat().replace("+00:00", "")],
    ] * MOEX_PAGE_SIZE
    page_two = [
        [101.0, 102.0, 103.0, 100.0, 0, fake.pyfloat(min_value=10, max_value=20, positive=True), (start + timedelta(hours=4)).isoformat().replace("+00:00", "")],
        [None, 102.0, 103.0, 100.0, 0, 10.0, (start + timedelta(hours=5)).isoformat().replace("+00:00", "")],
    ]
    responses = iter(
        [
            _response(payload={"candles": {"data": page_one}}),
            _response(payload={"candles": {"data": page_two}}),
        ]
    )

    async def success_request(url: str, **kwargs):
        assert url.endswith("/IMOEX/candles.json")
        return next(responses)

    monkeypatch.setattr(source, "request", success_request)
    bars = await source.fetch_bars(coin, "4h", start, end)
    assert len(bars) == 2
    assert bars[0].close == 101.0

    responses = iter([_response(payload={"candles": {"data": []}})])
    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=next(responses)))
    assert await source.fetch_bars(coin, "1h", start, end) == []

    responses = iter(
        [
            _response(
                payload={
                    "candles": {
                        "data": [
                            [100.0, 101.0, None, None, 0, None, start.isoformat().replace("+00:00", "")],
                        ]
                    }
                }
            )
        ]
    )
    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=next(responses)))
    regular_bars = await source.fetch_bars(coin, "1h", start, end)
    assert len(regular_bars) == 1
    assert regular_bars[0].high == 100.0
    assert regular_bars[0].volume is None

    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(_coin(symbol="BTCUSD", asset_type="crypto"), "1h", start, end)
    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(coin, "15m", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=404)))
    with pytest.raises(UnsupportedMarketSourceQuery):
        await source.fetch_bars(coin, "1h", start, end)

    monkeypatch.setattr(source, "request", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=_response(status_code=500)))
    with pytest.raises(TemporaryMarketSourceError, match="moex http error: 500"):
        await source.fetch_bars(coin, "1h", start, end)
