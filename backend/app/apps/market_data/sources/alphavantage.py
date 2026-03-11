from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from app.core.settings import get_settings
from app.apps.market_data.domain import align_timestamp, ensure_utc, normalize_interval
from app.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)

if TYPE_CHECKING:
    from app.apps.market_data.models import Coin


ALPHA_VANTAGE_FOREX_PAIRS: dict[str, tuple[str, str]] = {
    "EURUSD": ("EUR", "USD"),
    "USDCNY": ("USD", "CNY"),
    "USDRUB": ("USD", "RUB"),
}

ALPHA_VANTAGE_INTRADAY_INTERVALS: dict[str, str] = {
    "15m": "15min",
    "1h": "60min",
    "4h": "60min",
}


class AlphaVantageForexMarketSource(BaseMarketSource):
    name = "alphavantage"
    asset_types = {"forex"}
    supported_intervals = {"1d"}
    base_url = "https://www.alphavantage.co/query"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_settings().alpha_vantage_api_key.strip()

    def supports_coin(self, coin: "Coin", interval: str) -> bool:
        if not self.api_key:
            return False
        return super().supports_coin(coin, interval)

    def get_symbol(self, coin: "Coin") -> str | None:
        pair = ALPHA_VANTAGE_FOREX_PAIRS.get(coin.symbol)
        if pair is None:
            return None
        return f"{pair[0]}/{pair[1]}"

    def bars_per_request(self, interval: str) -> int:
        normalized_interval = normalize_interval(interval)
        if normalized_interval == "1d":
            return 5000
        return 100

    def allows_terminal_gap(self, coin: "Coin") -> bool:
        del coin
        return True

    def _request_payload(self, params: dict[str, str]) -> dict[str, object]:
        try:
            response = self.request(
                self.base_url,
                params=params,
                fallback_retry_after_seconds=300,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        if "Note" in payload:
            self.raise_rate_limited(retry_after_seconds=300, message=f"{self.name} rate limited")
        if "Information" in payload:
            information = str(payload["Information"])
            information_lower = information.lower()
            if "premium endpoint" in information_lower or "subscribe" in information_lower:
                raise UnsupportedMarketSourceQuery(information)
            if "free api key" in information_lower:
                raise UnsupportedMarketSourceQuery(information)
            raise TemporaryMarketSourceError(information)
        if "Error Message" in payload:
            raise UnsupportedMarketSourceQuery(str(payload["Error Message"]))
        return payload

    def _parse_intraday_payload(
        self,
        payload: dict[str, object],
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        interval_key = ALPHA_VANTAGE_INTRADAY_INTERVALS[normalize_interval(interval)]
        series_key = f"Time Series FX ({interval_key})"
        series = payload.get(series_key)
        if not isinstance(series, dict):
            return []

        bars: list[MarketBar] = []
        for timestamp_raw, item in series.items():
            if not isinstance(item, dict):
                continue
            try:
                timestamp = ensure_utc(datetime.fromisoformat(str(timestamp_raw).replace(" ", "T")))
                open_raw = item["1. open"]
                high_raw = item["2. high"]
                low_raw = item["3. low"]
                close_raw = item["4. close"]
            except Exception:
                continue
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=float(open_raw),
                    high=float(high_raw),
                    low=float(low_raw),
                    close=float(close_raw),
                    volume=None,
                    source=self.name,
                ),
            )
        bars.sort(key=lambda bar: bar.timestamp)
        bars = [bar for bar in bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]
        if normalize_interval(interval) == "4h":
            return self._resample_four_hour_bars(bars, start, end)
        return bars

    def _parse_daily_payload(
        self,
        payload: dict[str, object],
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        series = payload.get("Time Series FX (Daily)")
        if not isinstance(series, dict):
            return []

        bars: list[MarketBar] = []
        for timestamp_raw, item in series.items():
            if not isinstance(item, dict):
                continue
            try:
                timestamp = ensure_utc(datetime.fromisoformat(f"{timestamp_raw}T00:00:00"))
                open_raw = item["1. open"]
                high_raw = item["2. high"]
                low_raw = item["3. low"]
                close_raw = item["4. close"]
            except Exception:
                continue
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=float(open_raw),
                    high=float(high_raw),
                    low=float(low_raw),
                    close=float(close_raw),
                    volume=None,
                    source=self.name,
                ),
            )
        bars.sort(key=lambda bar: bar.timestamp)
        return [bar for bar in bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]

    def fetch_bars(self, coin: "Coin", interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        pair = ALPHA_VANTAGE_FOREX_PAIRS.get(coin.symbol)
        if pair is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")

        normalized_interval = normalize_interval(interval)
        base_symbol, quote_symbol = pair

        if normalized_interval == "1d":
            payload = self._request_payload(
                {
                    "function": "FX_DAILY",
                    "from_symbol": base_symbol,
                    "to_symbol": quote_symbol,
                    "outputsize": "full",
                    "apikey": self.api_key,
                }
            )
            return self._parse_daily_payload(payload, start, end)

        payload = self._request_payload(
            {
                "function": "FX_INTRADAY",
                "from_symbol": base_symbol,
                "to_symbol": quote_symbol,
                "interval": ALPHA_VANTAGE_INTRADAY_INTERVALS[normalized_interval],
                "outputsize": "full",
                "apikey": self.api_key,
            }
        )
        return self._parse_intraday_payload(payload, normalized_interval, start, end)

    def _resample_four_hour_bars(self, bars: list[MarketBar], start: datetime, end: datetime) -> list[MarketBar]:
        grouped: dict[datetime, list[MarketBar]] = defaultdict(list)
        for bar in bars:
            bucket = align_timestamp(bar.timestamp, "4h")
            grouped[bucket].append(bar)

        resampled: list[MarketBar] = []
        for bucket in sorted(grouped):
            group = sorted(grouped[bucket], key=lambda item: item.timestamp)
            if not group:
                continue
            resampled.append(
                MarketBar(
                    timestamp=bucket,
                    open=group[0].open,
                    high=max(item.high for item in group),
                    low=min(item.low for item in group),
                    close=group[-1].close,
                    volume=None,
                    source=self.name,
                )
            )
        return [bar for bar in resampled if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]
