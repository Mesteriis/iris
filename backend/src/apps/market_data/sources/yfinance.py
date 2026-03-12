from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import httpx

from src.apps.market_data.domain import align_timestamp, ensure_utc, interval_delta, normalize_interval
from src.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


YAHOO_SYMBOLS: dict[str, str] = {
    "AKTUSD": "AKT-USD",
    "BTCUSD": "BTC-USD",
    "DOGEUSD": "DOGE-USD",
    "ETHBTC": "ETH-BTC",
    "ETHUSD": "ETH-USD",
    "DJI": "^DJI",
    "EURUSD": "EURUSD=X",
    "DXY": "DX-Y.NYB",
    "GDAXI": "^GDAXI",
    "GSPC": "^GSPC",
    "NDX": "^NDX",
    "SOLUSD": "SOL-USD",
    "STOXX50E": "^STOXX50E",
    "TNX": "^TNX",
    "USDRUB": "RUB=X",
    "USDCNY": "CNY=X",
    "VIX": "^VIX",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "NATGASUSD": "NG=F",
    "BRENTUSD": "BZ=F",
    "WTIUSD": "CL=F",
}

YAHOO_INTERVALS: dict[str, str] = {
    "15m": "15m",
    "1h": "60m",
    "4h": "60m",
    "1d": "1d",
}

YAHOO_CHUNK_DAYS: dict[str, int] = {
    "15m": 45,
    "1h": 365,
    "4h": 365,
    "1d": 2000,
}


class YahooMarketSource(BaseMarketSource):
    name = "yahoo"
    asset_types = {"crypto", "forex", "index", "metal", "energy"}
    supported_intervals = {"15m", "1h", "4h", "1d"}
    base_url = "https://query2.finance.yahoo.com/v8/finance/chart"

    def __init__(self) -> None:
        super().__init__()
        self.client.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/136.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def get_symbol(self, coin: "Coin") -> str | None:
        return YAHOO_SYMBOLS.get(coin.symbol)

    def bars_per_request(self, interval: str) -> int:
        days = YAHOO_CHUNK_DAYS[normalize_interval(interval)]
        return max(int(days * timedelta(days=1) / interval_delta(interval)), 1)

    def allows_terminal_gap(self, coin: "Coin") -> bool:
        return coin.asset_type != "crypto"

    async def fetch_bars(self, coin: "Coin", interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        symbol = self.get_symbol(coin)
        if symbol is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")

        normalized_interval = normalize_interval(interval)
        raw_interval = YAHOO_INTERVALS[normalized_interval]
        url = f"{self.base_url}/{symbol}"
        params = {
            "period1": int(ensure_utc(start).timestamp()),
            "period2": int((ensure_utc(end) + interval_delta(normalized_interval)).timestamp()),
            "interval": raw_interval,
            "includePrePost": "false",
            "events": "div,splits",
        }

        try:
            response = await self.request(
                url,
                params=params,
                fallback_retry_after_seconds=300,
            )
            if response.status_code in {400, 404}:
                raise UnsupportedMarketSourceQuery(f"{self.name} rejected params for {coin.symbol}.")
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        chart = payload.get("chart", {})
        if chart.get("error"):
            raise TemporaryMarketSourceError(f"{self.name} api error: {chart['error']}")

        results = chart.get("result") or []
        if not results:
            return []

        result = results[0]
        timestamps = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        opens = quotes.get("open") or []
        highs = quotes.get("high") or []
        lows = quotes.get("low") or []
        closes = quotes.get("close") or []
        volumes = quotes.get("volume") or []

        bars: list[MarketBar] = []
        for index, timestamp_raw in enumerate(timestamps):
            if index >= len(opens) or closes[index] is None or opens[index] is None:
                continue
            timestamp = datetime.fromtimestamp(int(timestamp_raw), tz=ensure_utc(start).tzinfo)
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=float(opens[index]),
                    high=float(highs[index]) if highs[index] is not None else float(opens[index]),
                    low=float(lows[index]) if lows[index] is not None else float(opens[index]),
                    close=float(closes[index]),
                    volume=float(volumes[index]) if index < len(volumes) and volumes[index] is not None else None,
                    source=self.name,
                ),
            )

        bars.sort(key=lambda bar: bar.timestamp)
        if normalized_interval == "4h":
            return self._resample_four_hour_bars(bars, start, end)
        return [bar for bar in bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]

    def _resample_four_hour_bars(self, bars: list[MarketBar], start: datetime, end: datetime) -> list[MarketBar]:
        grouped: dict[datetime, list[MarketBar]] = defaultdict(list)
        for bar in bars:
            bucket = align_timestamp(bar.timestamp, "4h")
            grouped[bucket].append(bar)

        resampled: list[MarketBar] = []
        for bucket in sorted(grouped):
            group = sorted(grouped[bucket], key=lambda item: item.timestamp)
            resampled.append(
                MarketBar(
                    timestamp=bucket,
                    open=group[0].open,
                    high=max(item.high for item in group),
                    low=min(item.low for item in group),
                    close=group[-1].close,
                    volume=sum(item.volume or 0.0 for item in group),
                    source=self.name,
                ),
            )
        return [bar for bar in resampled if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]
