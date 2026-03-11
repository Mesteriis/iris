from __future__ import annotations

from typing import Type

from app.exchanges.base import ExchangePlugin
from app.models.exchange_account import ExchangeAccount

_REGISTRY: dict[str, Type[ExchangePlugin]] = {}


def register_exchange(name: str, plugin_cls: Type[ExchangePlugin]) -> None:
    _REGISTRY[name.strip().lower()] = plugin_cls


def get_exchange_plugin(name: str) -> Type[ExchangePlugin] | None:
    return _REGISTRY.get(name.strip().lower())


def create_exchange_plugin(account: ExchangeAccount) -> ExchangePlugin:
    plugin_cls = get_exchange_plugin(account.exchange_name)
    if plugin_cls is None:
        raise ValueError(f"Unsupported exchange '{account.exchange_name}'.")
    return plugin_cls(account)


def list_registered_exchanges() -> dict[str, Type[ExchangePlugin]]:
    return dict(sorted(_REGISTRY.items()))


from app.exchanges import binance, bybit  # noqa: E402,F401
