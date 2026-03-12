from __future__ import annotations

import pytest

from src.apps.portfolio.clients import BinancePlugin, BybitPlugin, ExchangePlugin, create_exchange_plugin, get_exchange_plugin, list_registered_exchanges, register_exchange
from src.apps.portfolio.models import ExchangeAccount


class DummyExchangePlugin:
    def __init__(self, account: ExchangeAccount) -> None:
        self.account = account

    async def fetch_balances(self):
        return []

    async def fetch_positions(self):
        return []

    async def fetch_orders(self):
        return []

    async def fetch_trades(self):
        return []


def test_exchange_plugin_registry_loads_builtin_and_custom_plugins() -> None:
    builtins = list_registered_exchanges()
    assert "bybit" in builtins
    assert "binance" in builtins

    register_exchange("fixture", DummyExchangePlugin)
    plugin_cls = list_registered_exchanges()["fixture"]
    account = ExchangeAccount(
        exchange_name="fixture",
        account_name="paper",
        api_key="key",
        api_secret="secret",
        enabled=True,
    )
    plugin = create_exchange_plugin(account)

    assert plugin_cls is DummyExchangePlugin
    assert isinstance(plugin, DummyExchangePlugin)
    assert plugin.account.exchange_name == "fixture"


@pytest.mark.asyncio
async def test_exchange_plugin_registry_covers_builtin_plugins_and_error_paths() -> None:
    assert get_exchange_plugin(" BINANCE ") is BinancePlugin
    assert get_exchange_plugin("ByBit") is BybitPlugin

    binance_account = ExchangeAccount(exchange_name="binance", account_name="swing", enabled=True)
    bybit_account = ExchangeAccount(exchange_name="bybit", account_name="hedge", enabled=True)
    assert await BinancePlugin(binance_account).fetch_balances() == []
    assert await BinancePlugin(binance_account).fetch_positions() == []
    assert await BinancePlugin(binance_account).fetch_orders() == []
    assert await BinancePlugin(binance_account).fetch_trades() == []
    assert await BybitPlugin(bybit_account).fetch_balances() == []
    assert await BybitPlugin(bybit_account).fetch_positions() == []
    assert await BybitPlugin(bybit_account).fetch_orders() == []
    assert await BybitPlugin(bybit_account).fetch_trades() == []

    with pytest.raises(NotImplementedError):
        await ExchangePlugin.fetch_balances(object())
    with pytest.raises(NotImplementedError):
        await ExchangePlugin.fetch_positions(object())
    with pytest.raises(NotImplementedError):
        await ExchangePlugin.fetch_orders(object())
    with pytest.raises(NotImplementedError):
        await ExchangePlugin.fetch_trades(object())

    with pytest.raises(ValueError, match="Unsupported exchange"):
        create_exchange_plugin(ExchangeAccount(exchange_name="unknown", account_name="paper", enabled=True))
