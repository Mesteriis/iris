from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.apps.portfolio.models import ExchangeAccount


class ExchangePlugin(ABC):
    def __init__(self, account: ExchangeAccount) -> None:
        self.account = account

    @abstractmethod
    async def fetch_balances(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_orders(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_trades(self) -> list[dict[str, Any]]:
        raise NotImplementedError


_REGISTRY: dict[str, type[ExchangePlugin]] = {}


def register_exchange(name: str, plugin_cls: type[ExchangePlugin]) -> None:
    _REGISTRY[name.strip().lower()] = plugin_cls


def get_exchange_plugin(name: str) -> type[ExchangePlugin] | None:
    return _REGISTRY.get(name.strip().lower())


def create_exchange_plugin(account: ExchangeAccount) -> ExchangePlugin:
    plugin_cls = get_exchange_plugin(account.exchange_name)
    if plugin_cls is None:
        raise ValueError(f"Unsupported exchange '{account.exchange_name}'.")
    return plugin_cls(account)


def list_registered_exchanges() -> dict[str, type[ExchangePlugin]]:
    return dict(sorted(_REGISTRY.items()))


class BinancePlugin(ExchangePlugin):
    async def fetch_balances(self) -> list[dict[str, Any]]:
        return []

    async def fetch_positions(self) -> list[dict[str, Any]]:
        return []

    async def fetch_orders(self) -> list[dict[str, Any]]:
        return []

    async def fetch_trades(self) -> list[dict[str, Any]]:
        return []


class BybitPlugin(ExchangePlugin):
    async def fetch_balances(self) -> list[dict[str, Any]]:
        return []

    async def fetch_positions(self) -> list[dict[str, Any]]:
        return []

    async def fetch_orders(self) -> list[dict[str, Any]]:
        return []

    async def fetch_trades(self) -> list[dict[str, Any]]:
        return []


register_exchange("binance", BinancePlugin)
register_exchange("bybit", BybitPlugin)


__all__ = [
    "BinancePlugin",
    "BybitPlugin",
    "ExchangePlugin",
    "create_exchange_plugin",
    "get_exchange_plugin",
    "list_registered_exchanges",
    "register_exchange",
]
