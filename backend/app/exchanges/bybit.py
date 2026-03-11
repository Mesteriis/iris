from __future__ import annotations

from typing import Any

from app.exchanges.base import ExchangePlugin
from app.exchanges.registry import register_exchange


class BybitPlugin(ExchangePlugin):
    async def fetch_balances(self) -> list[dict[str, Any]]:
        return []

    async def fetch_positions(self) -> list[dict[str, Any]]:
        return []

    async def fetch_orders(self) -> list[dict[str, Any]]:
        return []

    async def fetch_trades(self) -> list[dict[str, Any]]:
        return []


register_exchange("bybit", BybitPlugin)
