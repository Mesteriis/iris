from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.exchange_account import ExchangeAccount


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
