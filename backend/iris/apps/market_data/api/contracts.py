from typing import Literal

from iris.apps.market_data.schemas import CoinCreate, CoinRead, PriceHistoryCreate, PriceHistoryRead
from iris.core.http.contracts import AcceptedResponse


class CoinJobAcceptedRead(AcceptedResponse):
    operation_type: Literal["market_data.coin_history.sync"] = "market_data.coin_history.sync"
    symbol: str
    mode: Literal["auto", "backfill", "latest"]
    force: bool


__all__ = [
    "CoinCreate",
    "CoinJobAcceptedRead",
    "CoinRead",
    "PriceHistoryCreate",
    "PriceHistoryRead",
]
