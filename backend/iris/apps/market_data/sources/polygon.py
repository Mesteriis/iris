from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import httpx

from iris.apps.market_data.domain import align_timestamp, ensure_utc, normalize_interval
from iris.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)
from iris.core.settings import get_settings

if TYPE_CHECKING:
    from iris.apps.market_data.models import Coin


POLYGON_SYMBOLS: dict[str, str] = {
    "DJI": "I:DJI",
    "DXY": "I:DXY",
    "EURUSD": "C:EURUSD",
    "GSPC": "I:SPX",
    "NDX": "I:NDX",
    "TNX": "I:TNX",
    "USDCNY": "C:USDCNY",
    "USDRUB": "C:USDRUB",
    "VIX": "I:VIX",
}

POLYGON_INTERVALS: dict[str, tuple[int, str]] = {
    "15m": (15, "minute"),
    "1h": (1, "hour"),
    "4h": (4, "hour"),
    "1d": (1, "day"),
}


class PolygonMarketSource(BaseMarketSource):
    name = "polygon"
    asset_types: ClassVar[set[str]] = {"forex", "index"}
    supported_intervals: ClassVar[set[str]] = {"15m", "1h", "4h", "1d"}
    base_url = "https://api.polygon.io/v2/aggs/ticker"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_settings().polygon_api_key.strip()

    def supports_coin(self, coin: Coin, interval: str) -> bool:
        if not self.api_key:
            return False
        return super().supports_coin(coin, interval)

    def get_symbol(self, coin: Coin) -> str | None:
        return self.resolve_provider_symbol(coin.symbol, fallback=POLYGON_SYMBOLS.get(coin.symbol))

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

        normalized_interval = normalize_interval(interval)
        multiplier, timespan = POLYGON_INTERVALS[normalized_interval]
        start_ts = int(ensure_utc(start).timestamp() * 1000)
        end_ts = int(ensure_utc(end).timestamp() * 1000)
        url = f"{self.base_url}/{symbol}/range/{multiplier}/{timespan}/{start_ts}/{end_ts}"

        try:
            response = await self.request(
                url,
                params={
                    "sort": "asc",
                    "limit": min(self._limit_for_range(normalized_interval, start, end), self.bars_per_request(normalized_interval)),
                    "adjusted": "false",
                    "apiKey": self.api_key,
                },
                fallback_retry_after_seconds=60,
            )
            if response.status_code in {400, 401, 403, 404}:
                message = f"{self.name} rejected params for {coin.symbol}."
                try:
                    payload = response.json()
                except Exception:
                    payload = {}
                if isinstance(payload, dict):
                    raw_message = payload.get("message")
                    if raw_message:
                        message = str(raw_message)
                raise UnsupportedMarketSourceQuery(message)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        status = str(payload.get("status") or "").lower()
        if status not in {"ok", "delayed"}:
            message = str(payload.get("error") or payload.get("message") or f"{self.name} returned an error")
            message_lower = message.lower()
            if "unknown api key" in message_lower or "not authorized" in message_lower:
                raise UnsupportedMarketSourceQuery(message)
            raise TemporaryMarketSourceError(message)

        bars: list[MarketBar] = []
        for item in payload.get("results", []) or []:
            timestamp_raw = item.get("t")
            open_raw = item.get("o")
            high_raw = item.get("h")
            low_raw = item.get("l")
            close_raw = item.get("c")
            if not all(value is not None for value in (timestamp_raw, open_raw, high_raw, low_raw, close_raw)):
                continue
            timestamp = ensure_utc(datetime.fromtimestamp(int(timestamp_raw) / 1000))
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=float(open_raw),
                    high=float(high_raw),
                    low=float(low_raw),
                    close=float(close_raw),
                    volume=float(item["v"]) if item.get("v") is not None else None,
                    source=self.name,
                )
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
                    volume=sum(item.volume or 0.0 for item in group) if any(item.volume is not None for item in group) else None,
                    source=self.name,
                )
            )

        return [bar for bar in resampled if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]
