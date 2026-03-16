from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING, ClassVar

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


STOOQ_SYMBOLS: dict[str, str] = {
    "DJI": "^dji",
    "GDAXI": "^dax",
    "GSPC": "^spx",
    "XAGUSD": "xagusd",
}


class StooqMarketSource(BaseMarketSource):
    name = "stooq"
    asset_types: ClassVar[set[str]] = {"index", "metal"}
    supported_intervals: ClassVar[set[str]] = {"1d"}
    base_url = "https://stooq.com/q/d/l/"
    proxy_pool_mode = "fallback"

    def get_symbol(self, coin: Coin) -> str | None:
        return self.resolve_provider_symbol(coin.symbol, fallback=STOOQ_SYMBOLS.get(coin.symbol))

    def bars_per_request(self, interval: str) -> int:
        del interval
        return 50_000

    def allows_terminal_gap(self, coin: Coin) -> bool:
        del coin
        return True

    async def fetch_bars(self, coin: Coin, interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        symbol = self.get_symbol(coin)
        if symbol is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")
        if normalize_interval(interval) != "1d":
            raise UnsupportedMarketSourceQuery(f"{self.name} only supports daily history for {coin.symbol}.")

        try:
            response = await self.request(
                self.base_url,
                params={"s": symbol, "i": "d"},
                headers={"Accept": "text/csv,text/plain;q=0.9,*/*;q=0.8"},
                fallback_retry_after_seconds=60,
            )
            if response.status_code in {400, 404}:
                raise UnsupportedMarketSourceQuery(f"{self.name} rejected params for {coin.symbol}.")
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        payload = response.text.strip()
        if not payload:
            return []
        if payload.lower() == "no data":
            raise UnsupportedMarketSourceQuery(f"{self.name} returned no data for {coin.symbol}.")

        try:
            reader = csv.DictReader(StringIO(payload))
        except csv.Error as exc:
            raise TemporaryMarketSourceError(f"{self.name} csv error: {exc}") from exc

        if reader.fieldnames is None or "Date" not in reader.fieldnames:
            raise TemporaryMarketSourceError(f"{self.name} returned an unexpected payload for {coin.symbol}.")

        bars: list[MarketBar] = []
        for row in reader:
            date_raw = row.get("Date")
            open_raw = row.get("Open")
            high_raw = row.get("High")
            low_raw = row.get("Low")
            close_raw = row.get("Close")
            if not all(value for value in (date_raw, open_raw, high_raw, low_raw, close_raw)):
                continue
            try:
                timestamp = ensure_utc(datetime.fromisoformat(str(date_raw)))
                volume_raw = row.get("Volume")
                bars.append(
                    MarketBar(
                        timestamp=timestamp,
                        open=float(open_raw),
                        high=float(high_raw),
                        low=float(low_raw),
                        close=float(close_raw),
                        volume=float(volume_raw) if volume_raw not in {None, ""} else None,
                        source=self.name,
                    )
                )
            except ValueError as exc:
                raise TemporaryMarketSourceError(f"{self.name} parse error: {exc}") from exc

        bars.sort(key=lambda bar: bar.timestamp)
        return [bar for bar in bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]
