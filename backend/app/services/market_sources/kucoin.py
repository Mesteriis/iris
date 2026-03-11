from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from app.services.market_data import ensure_utc, normalize_interval
from app.services.market_sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)

if TYPE_CHECKING:
    from app.models.coin import Coin


KUCOIN_SYMBOLS: dict[str, str] = {
    "BTCUSD": "BTC-USDT",
    "DOGEUSD": "DOGE-USDT",
    "ETHUSD": "ETH-USDT",
    "FETUSD": "FET-USDT",
    "RENDERUSD": "RENDER-USDT",
    "SOLUSD": "SOL-USDT",
    "TAOUSD": "TAO-USDT",
    "AKTUSD": "AKT-USDT",
}

KUCOIN_INTERVALS: dict[str, str] = {
    "15m": "15min",
    "1h": "1hour",
    "4h": "4hour",
    "1d": "1day",
}


class KucoinMarketSource(BaseMarketSource):
    name = "kucoin"
    asset_types = {"crypto"}
    supported_intervals = {"15m", "1h", "4h", "1d"}
    base_url = "https://api.kucoin.com/api/v1/market/candles"

    def get_symbol(self, coin: "Coin") -> str | None:
        return KUCOIN_SYMBOLS.get(coin.symbol)

    def bars_per_request(self, interval: str) -> int:
        return 500

    def fetch_bars(self, coin: "Coin", interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        symbol = self.get_symbol(coin)
        if symbol is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")

        normalized_interval = normalize_interval(interval)
        kucoin_interval = KUCOIN_INTERVALS[normalized_interval]
        params = {
            "symbol": symbol,
            "type": kucoin_interval,
            "startAt": int(ensure_utc(start).timestamp()),
            "endAt": int(ensure_utc(end).timestamp()),
        }

        try:
            response = self.request(self.base_url, params=params)
            if response.status_code in {400, 404}:
                raise UnsupportedMarketSourceQuery(f"{self.name} rejected params for {coin.symbol}.")
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        if payload.get("code") != "200000":
            raise TemporaryMarketSourceError(f"{self.name} api error: {payload.get('msg', 'unknown')}")

        bars: list[MarketBar] = []
        for item in payload.get("data", []):
            timestamp = datetime.fromtimestamp(float(item[0]), tz=ensure_utc(start).tzinfo)
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=float(item[1]),
                    high=float(item[3]),
                    low=float(item[4]),
                    close=float(item[2]),
                    volume=float(item[5]),
                    source=self.name,
                ),
            )
        bars.sort(key=lambda bar: bar.timestamp)
        return bars[-self.bars_per_request(normalized_interval) :]
