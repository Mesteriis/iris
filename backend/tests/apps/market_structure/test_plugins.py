from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.apps.market_structure.exceptions import InvalidMarketStructureSourceConfigurationError
from src.apps.market_structure.models import MarketStructureSource
from src.apps.market_structure.plugins import (
    BinanceUsdMarketStructurePlugin,
    BybitDerivativesMarketStructurePlugin,
    ManualPushMarketStructurePlugin,
    list_registered_market_structure_plugins,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, params: dict[str, object] | None = None):
        if "premiumIndex" in url:
            assert params == {"symbol": "ETHUSDT"}
            return _FakeResponse(
                {
                    "symbol": "ETHUSDT",
                    "markPrice": "3125.5",
                    "indexPrice": "3118.0",
                    "lastFundingRate": "0.00095",
                    "time": 1760000000000,
                }
            )
        if "openInterest" in url:
            assert params == {"symbol": "ETHUSDT"}
            return _FakeResponse({"openInterest": "18234.1", "symbol": "ETHUSDT", "time": 1760000001000})
        if "v5/market/tickers" in url:
            return _FakeResponse(
                {
                    "retCode": 0,
                    "time": 1760000002000,
                    "result": {
                        "list": [
                            {
                                "symbol": "ETHUSDT",
                                "lastPrice": "3124.1",
                                "markPrice": "3125.2",
                                "indexPrice": "3119.4",
                                "fundingRate": "0.00088",
                                "openInterest": "14321.8",
                                "basis": "0.00186",
                                "volume24h": "982341.7",
                            }
                        ]
                    },
                }
            )
        raise AssertionError(f"Unexpected URL {url}")


def _source(plugin_name: str, *, settings: dict[str, object]) -> MarketStructureSource:
    return MarketStructureSource(
        plugin_name=plugin_name,
        display_name=f"{plugin_name}-feed",
        enabled=True,
        auth_mode="public",
        credentials_json={},
        settings_json=settings,
        cursor_json={},
    )


def test_built_in_market_structure_plugins_are_registered() -> None:
    plugins = list_registered_market_structure_plugins()

    assert {"binance_usdm", "bybit_derivatives", "manual_push"} <= set(plugins)
    assert plugins["manual_push"].descriptor.supports_polling is False
    assert plugins["manual_push"].descriptor.supports_manual_ingest is True


def test_plugins_validate_required_fields() -> None:
    BinanceUsdMarketStructurePlugin.validate_configuration(
        credentials={},
        settings={"coin_symbol": "ETHUSD_EVT", "market_symbol": "ETHUSDT", "timeframe": 15},
    )
    BybitDerivativesMarketStructurePlugin.validate_configuration(
        credentials={},
        settings={"coin_symbol": "ETHUSD_EVT", "market_symbol": "ETHUSDT", "timeframe": 15},
    )
    ManualPushMarketStructurePlugin.validate_configuration(
        credentials={},
        settings={"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "venue": "liqscope"},
    )

    with pytest.raises(InvalidMarketStructureSourceConfigurationError, match="market_symbol"):
        BinanceUsdMarketStructurePlugin.validate_configuration(
            credentials={},
            settings={"coin_symbol": "ETHUSD_EVT", "timeframe": 15},
        )


@pytest.mark.asyncio
async def test_binance_and_bybit_plugins_parse_market_snapshots(monkeypatch) -> None:
    monkeypatch.setattr("src.apps.market_structure.plugins.httpx.AsyncClient", _FakeAsyncClient)

    binance_snapshot = (
        await BinanceUsdMarketStructurePlugin(
            _source(
                "binance_usdm",
                settings={"coin_symbol": "ETHUSD_EVT", "market_symbol": "ETHUSDT", "timeframe": 15},
            )
        ).fetch_snapshots(cursor={}, limit=1)
    ).snapshots[0]
    bybit_snapshot = (
        await BybitDerivativesMarketStructurePlugin(
            _source(
                "bybit_derivatives",
                settings={"coin_symbol": "ETHUSD_EVT", "market_symbol": "ETHUSDT", "timeframe": 15},
            )
        ).fetch_snapshots(cursor={}, limit=1)
    ).snapshots[0]

    assert binance_snapshot.venue == "binance_usdm"
    assert binance_snapshot.timestamp > datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert binance_snapshot.funding_rate == pytest.approx(0.00095)
    assert binance_snapshot.open_interest == pytest.approx(18234.1)
    assert binance_snapshot.basis is not None and binance_snapshot.basis > 0

    assert bybit_snapshot.venue == "bybit_derivatives"
    assert bybit_snapshot.last_price == pytest.approx(3124.1)
    assert bybit_snapshot.open_interest == pytest.approx(14321.8)
    assert bybit_snapshot.volume == pytest.approx(982341.7)
