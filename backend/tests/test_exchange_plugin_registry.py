from __future__ import annotations

from app.exchanges.registry import create_exchange_plugin, list_registered_exchanges, register_exchange
from app.models.exchange_account import ExchangeAccount


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
