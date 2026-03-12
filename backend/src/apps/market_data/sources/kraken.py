from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from src.apps.market_data.domain import ensure_utc, interval_delta, normalize_interval
from src.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


KRAKEN_SYMBOLS: dict[str, str] = {
    "BTCUSD": "XXBTZUSD",
    "ETHUSD": "XETHZUSD",
}

KRAKEN_INTERVALS: dict[str, int] = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class KrakenMarketSource(BaseMarketSource):
    name = "kraken"
    asset_types = {"crypto"}
    supported_intervals = {"15m", "1h", "4h", "1d"}
    base_url = "https://api.kraken.com/0/public/OHLC"

    def get_symbol(self, coin: "Coin") -> str | None:
        return KRAKEN_SYMBOLS.get(coin.symbol)

    def bars_per_request(self, interval: str) -> int:
        return 720

    async def fetch_bars(self, coin: "Coin", interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        symbol = self.get_symbol(coin)
        if symbol is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")

        normalized_interval = normalize_interval(interval)
        max_span = interval_delta(normalized_interval) * self.bars_per_request(normalized_interval)
        if ensure_utc(end) - ensure_utc(start) > max_span:
            raise UnsupportedMarketSourceQuery(f"{self.name} cannot backfill that far for {coin.symbol}.")

        params = {
            "pair": symbol,
            "interval": KRAKEN_INTERVALS[normalized_interval],
            "since": int(ensure_utc(start).timestamp()),
        }

        try:
            response = await self.request(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        if payload.get("error"):
            raise TemporaryMarketSourceError(f"{self.name} api error: {payload['error']}")

        result = payload.get("result", {})
        pair_key = next((key for key in result.keys() if key != "last"), None)
        if pair_key is None:
            return []

        bars: list[MarketBar] = []
        for item in result[pair_key]:
            timestamp = datetime.fromtimestamp(float(item[0]), tz=ensure_utc(start).tzinfo)
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[6]),
                    source=self.name,
                ),
            )
        bars.sort(key=lambda bar: bar.timestamp)
        return [bar for bar in bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]
