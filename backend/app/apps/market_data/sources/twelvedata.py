from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from app.core.settings import get_settings
from app.apps.market_data.domain import ensure_utc, normalize_interval
from app.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)

if TYPE_CHECKING:
    from app.apps.market_data.models import Coin


TWELVE_DATA_INTERVALS: dict[str, str] = {
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
}

TWELVE_DATA_SYMBOL_CANDIDATES: dict[str, list[str]] = {
    "DJI": ["DJI", "^DJI"],
    "DXY": ["DXY", "DX-Y.NYB"],
    "EURUSD": ["EUR/USD"],
    "GDAXI": ["GDAXI", "^GDAXI"],
    "GSPC": ["GSPC", "^GSPC"],
    "NDX": ["NDX", "^NDX"],
    "STOXX50E": ["STOXX50E", "^STOXX50E"],
    "TNX": ["TNX", "^TNX"],
    "USDCNY": ["USD/CNY"],
    "USDRUB": ["USD/RUB"],
    "VIX": ["VIX", "^VIX"],
    "XAGUSD": ["XAG/USD"],
    "XAUUSD": ["XAU/USD"],
}


class TwelveDataMarketSource(BaseMarketSource):
    name = "twelvedata"
    asset_types = {"forex", "index", "metal"}
    supported_intervals = {"15m", "1h", "4h", "1d"}
    base_url = "https://api.twelvedata.com/time_series"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_settings().twelve_data_api_key.strip()
        self._resolved_symbols: dict[str, str] = {}
        if self.api_key:
            self.client.headers.update({"Authorization": f"apikey {self.api_key}"})

    def supports_coin(self, coin: "Coin", interval: str) -> bool:
        if not self.api_key:
            return False
        return super().supports_coin(coin, interval)

    def get_symbol(self, coin: "Coin") -> str | None:
        resolved = self._resolved_symbols.get(coin.symbol)
        if resolved:
            return resolved

        candidates = TWELVE_DATA_SYMBOL_CANDIDATES.get(coin.symbol)
        if candidates:
            return candidates[0]
        return coin.symbol if coin.asset_type in self.asset_types else None

    def bars_per_request(self, interval: str) -> int:
        del interval
        return 5000

    def allows_terminal_gap(self, coin: "Coin") -> bool:
        del coin
        return True

    def _candidate_symbols(self, coin: "Coin") -> list[str]:
        candidates = TWELVE_DATA_SYMBOL_CANDIDATES.get(coin.symbol)
        if candidates:
            return candidates
        symbol = self.get_symbol(coin)
        return [symbol] if symbol else []

    def _request_symbol(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        params = {
            "symbol": symbol,
            "interval": TWELVE_DATA_INTERVALS[normalize_interval(interval)],
            "start_date": ensure_utc(start).strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": ensure_utc(end).strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": "UTC",
            "order": "ASC",
            "format": "JSON",
            "outputsize": min(self._limit_for_range(interval, start, end), self.bars_per_request(interval)),
        }

        try:
            response = self.request(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        if payload.get("status") == "error":
            code = int(payload.get("code") or 400)
            message = str(payload.get("message") or f"{self.name} returned an error")
            message_lower = message.lower()
            if code == 429 or "run out of api credits" in message_lower or "rate limit" in message_lower:
                self.raise_rate_limited(retry_after_seconds=60, message=f"{self.name} rate limited")
            if "available starting with grow" in message_lower or "consider upgrading" in message_lower:
                raise UnsupportedMarketSourceQuery(message)
            if code in {400, 401, 403, 404}:
                raise UnsupportedMarketSourceQuery(message)
            raise TemporaryMarketSourceError(message)

        bars: list[MarketBar] = []
        for item in payload.get("values", []) or []:
            timestamp_raw = item.get("datetime")
            open_raw = item.get("open")
            high_raw = item.get("high")
            low_raw = item.get("low")
            close_raw = item.get("close")
            if not all(value is not None for value in (timestamp_raw, open_raw, high_raw, low_raw, close_raw)):
                continue
            timestamp = ensure_utc(datetime.fromisoformat(str(timestamp_raw).replace(" ", "T")))
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=float(open_raw),
                    high=float(high_raw),
                    low=float(low_raw),
                    close=float(close_raw),
                    volume=float(item["volume"]) if item.get("volume") is not None else None,
                    source=self.name,
                ),
            )
        bars.sort(key=lambda bar: bar.timestamp)
        return [bar for bar in bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]

    def fetch_bars(self, coin: "Coin", interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        last_error: str | None = None
        for candidate in self._candidate_symbols(coin):
            try:
                bars = self._request_symbol(candidate, interval, start, end)
            except UnsupportedMarketSourceQuery as exc:
                last_error = str(exc)
                continue

            if bars:
                self._resolved_symbols[coin.symbol] = candidate
            return bars

        raise UnsupportedMarketSourceQuery(last_error or f"{self.name} does not support {coin.symbol}.")
