from __future__ import annotations

from typing import Literal

from src.apps.market_data.schemas import CoinCreate, CoinRead, PriceHistoryCreate, PriceHistoryRead
from src.core.http.contracts import HttpContract


class CoinJobQueuedRead(HttpContract):
    status: Literal["queued"] = "queued"
    symbol: str
    mode: Literal["auto", "backfill", "latest"]
    force: bool


__all__ = [
    "CoinCreate",
    "CoinJobQueuedRead",
    "CoinRead",
    "PriceHistoryCreate",
    "PriceHistoryRead",
]
