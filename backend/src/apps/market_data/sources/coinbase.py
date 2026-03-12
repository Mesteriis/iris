from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from src.apps.market_data.domain import ensure_utc, normalize_interval
from src.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


COINBASE_SYMBOLS: dict[str, str] = {
    "BTCUSD": "BTC-USD",
    "DOGEUSD": "DOGE-USD",
    "ETHUSD": "ETH-USD",
    "SOLUSD": "SOL-USD",
}

COINBASE_INTERVALS: dict[str, int] = {
    "15m": 900,
    "1h": 3600,
    "1d": 86400,
}


class CoinbaseMarketSource(BaseMarketSource):
    name = "coinbase"
    asset_types = {"crypto"}
    supported_intervals = {"15m", "1h", "1d"}
    base_url = "https://api.exchange.coinbase.com/products"

    def get_symbol(self, coin: "Coin") -> str | None:
        return COINBASE_SYMBOLS.get(coin.symbol)

    def bars_per_request(self, interval: str) -> int:
        return 300

    async def fetch_bars(self, coin: "Coin", interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        symbol = self.get_symbol(coin)
        if symbol is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")

        normalized_interval = normalize_interval(interval)
        granularity = COINBASE_INTERVALS.get(normalized_interval)
        if granularity is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {interval}.")

        url = f"{self.base_url}/{symbol}/candles"
        params = {
            "granularity": granularity,
            "start": ensure_utc(start).isoformat().replace("+00:00", "Z"),
            "end": ensure_utc(end).isoformat().replace("+00:00", "Z"),
        }

        try:
            response = await self.request(url, params=params)
            if response.status_code in {400, 404}:
                raise UnsupportedMarketSourceQuery(f"{self.name} rejected params for {coin.symbol}.")
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        bars: list[MarketBar] = []
        for item in payload:
            timestamp = datetime.fromtimestamp(int(item[0]), tz=ensure_utc(start).tzinfo)
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=float(item[3]),
                    high=float(item[2]),
                    low=float(item[1]),
                    close=float(item[4]),
                    volume=float(item[5]),
                    source=self.name,
                ),
            )
        bars.sort(key=lambda bar: bar.timestamp)
        return bars[-self.bars_per_request(normalized_interval) :]
