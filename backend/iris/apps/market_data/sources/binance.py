from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import httpx

from iris.apps.market_data.domain import ensure_utc, normalize_interval
from iris.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
    http_query_params,
)

if TYPE_CHECKING:
    from iris.apps.market_data.models import Coin


BINANCE_SYMBOLS: dict[str, str] = {
    "BTCUSD": "BTCUSDT",
    "DOGEUSD": "DOGEUSDT",
    "ETHUSD": "ETHUSDT",
    "ETHBTC": "ETHBTC",
    "FETUSD": "FETUSDT",
    "RENDERUSD": "RENDERUSDT",
    "SOLUSD": "SOLUSDT",
    "TAOUSD": "TAOUSDT",
}


class BinanceMarketSource(BaseMarketSource):
    name = "binance"
    asset_types: ClassVar[set[str]] = {"crypto"}
    supported_intervals: ClassVar[set[str]] = {"15m", "1h", "4h", "1d"}
    base_url = "https://api.binance.com/api/v3/klines"
    rate_limit_status_codes: ClassVar[set[int]] = {418, 429}

    def get_symbol(self, coin: Coin) -> str | None:
        return self.resolve_provider_symbol(coin.symbol, fallback=BINANCE_SYMBOLS.get(coin.symbol))

    def bars_per_request(self, interval: str) -> int:
        return 1000

    async def fetch_bars(self, coin: Coin, interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        symbol = self.get_symbol(coin)
        if symbol is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")

        normalized_interval = normalize_interval(interval)
        current = ensure_utc(start)
        limit = min(self._limit_for_range(normalized_interval, current, end), self.bars_per_request(normalized_interval))
        params = http_query_params(
            symbol=symbol,
            interval=normalized_interval,
            startTime=int(current.timestamp() * 1000),
            endTime=int(ensure_utc(end).timestamp() * 1000),
            limit=limit,
        )

        try:
            response = await self.request(self.base_url, params=params)
            if response.status_code == 400:
                raise UnsupportedMarketSourceQuery(f"{self.name} rejected params for {coin.symbol}.")
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        bars: list[MarketBar] = []
        for item in payload:
            timestamp = datetime.fromtimestamp(int(item[0]) / 1000, tz=current.tzinfo)
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[5]),
                    source=self.name,
                ),
            )
        bars.sort(key=lambda bar: bar.timestamp)
        return bars
