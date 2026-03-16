from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, NotRequired, TypedDict

import httpx

from iris.apps.market_data.domain import align_timestamp, ensure_utc, normalize_interval
from iris.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
    http_query_params,
)
from iris.apps.market_data.sources.rate_limits import HttpQueryParams, HttpQueryValue
from iris.core.settings import get_settings

if TYPE_CHECKING:
    from iris.apps.market_data.models import Coin


ALPHA_VANTAGE_FOREX_PAIRS: dict[str, tuple[str, str]] = {
    "EURUSD": ("EUR", "USD"),
    "USDCNY": ("USD", "CNY"),
    "USDRUB": ("USD", "RUB"),
}


class AlphaVantageSeriesSpec(TypedDict):
    function: str
    interval: str
    provider_symbol: str
    supported_intervals: set[str]
    maturity: NotRequired[str]


ALPHA_VANTAGE_SPECIAL_SERIES: dict[str, AlphaVantageSeriesSpec] = {
    "BRENTUSD": {
        "function": "BRENT",
        "interval": "daily",
        "provider_symbol": "BRENT",
        "supported_intervals": {"1d"},
    },
    "NATGASUSD": {
        "function": "NATURAL_GAS",
        "interval": "daily",
        "provider_symbol": "NATURAL_GAS",
        "supported_intervals": {"1d"},
    },
    "TNX": {
        "function": "TREASURY_YIELD",
        "interval": "daily",
        "maturity": "10year",
        "provider_symbol": "TREASURY_YIELD:10YEAR",
        "supported_intervals": {"1d"},
    },
    "WTIUSD": {
        "function": "WTI",
        "interval": "daily",
        "provider_symbol": "WTI",
        "supported_intervals": {"1d"},
    },
}

ALPHA_VANTAGE_INTRADAY_INTERVALS: dict[str, str] = {
    "15m": "15min",
    "1h": "60min",
    "4h": "60min",
}


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


@dataclass(frozen=True, slots=True)
class AlphaVantageQuery:
    kind: str
    provider_symbol: str
    supported_intervals: frozenset[str]
    function: str | None = None
    base_symbol: str | None = None
    quote_symbol: str | None = None
    interval: str | None = None
    maturity: str | None = None


class AlphaVantageMarketSource(BaseMarketSource):
    name = "alphavantage"
    asset_types: ClassVar[set[str]] = {"forex", "energy", "index"}
    supported_intervals: ClassVar[set[str]] = {"15m", "1h", "4h", "1d"}
    base_url = "https://www.alphavantage.co/query"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_settings().alpha_vantage_api_key.strip()

    def supports_coin(self, coin: Coin, interval: str) -> bool:
        if not self.api_key:
            return False
        query = self._resolve_query(coin)
        return query is not None and normalize_interval(interval) in query.supported_intervals

    def _resolve_pair(self, coin: Coin) -> tuple[str, str] | None:
        pair = ALPHA_VANTAGE_FOREX_PAIRS.get(coin.symbol)
        if pair is not None:
            return pair
        normalized_symbol = coin.symbol.strip().upper()
        if len(normalized_symbol) == 6 and self.supports_canonical_symbol(normalized_symbol):
            return normalized_symbol[:3], normalized_symbol[3:]
        return None

    def _resolve_query(self, coin: Coin) -> AlphaVantageQuery | None:
        pair = self._resolve_pair(coin)
        if pair is not None:
            return AlphaVantageQuery(
                kind="fx",
                provider_symbol=f"{pair[0]}/{pair[1]}",
                supported_intervals=frozenset({"15m", "1h", "4h", "1d"}),
                base_symbol=pair[0],
                quote_symbol=pair[1],
            )

        spec = ALPHA_VANTAGE_SPECIAL_SERIES.get(coin.symbol)
        if spec is None:
            return None
        return AlphaVantageQuery(
            kind="series",
            provider_symbol=spec["provider_symbol"],
            supported_intervals=frozenset(spec["supported_intervals"]),
            function=spec["function"],
            interval=spec["interval"],
            maturity=spec.get("maturity"),
        )

    def get_symbol(self, coin: Coin) -> str | None:
        query = self._resolve_query(coin)
        return query.provider_symbol if query is not None else None

    def bars_per_request(self, interval: str) -> int:
        normalized_interval = normalize_interval(interval)
        if normalized_interval == "1d":
            return 5000
        return 100

    def allows_terminal_gap(self, coin: Coin) -> bool:
        del coin
        return True

    async def _request_payload(self, params: HttpQueryParams) -> dict[str, object]:
        try:
            response = await self.request(
                self.base_url,
                params=params,
                fallback_retry_after_seconds=300,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        if not isinstance(payload, dict):
            raise TemporaryMarketSourceError(f"{self.name} returned an unexpected payload.")

        if "Note" in payload:
            await self.raise_rate_limited(retry_after_seconds=300, message=f"{self.name} rate limited")
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
        return {str(key): value for key, value in payload.items()}

    def _parse_intraday_entry(self, timestamp_raw: object, item: dict[object, object]) -> MarketBar | None:
        try:
            timestamp = ensure_utc(datetime.fromisoformat(str(timestamp_raw).replace(" ", "T")))
            open_raw = item["1. open"]
            high_raw = item["2. high"]
            low_raw = item["3. low"]
            close_raw = item["4. close"]
        except (KeyError, TypeError, ValueError):
            return None
        open_value = _float_or_none(open_raw)
        high_value = _float_or_none(high_raw)
        low_value = _float_or_none(low_raw)
        close_value = _float_or_none(close_raw)
        if open_value is None or high_value is None or low_value is None or close_value is None:
            return None
        return MarketBar(
            timestamp=timestamp,
            open=open_value,
            high=high_value,
            low=low_value,
            close=close_value,
            volume=None,
            source=self.name,
        )

    def _parse_daily_entry(self, timestamp_raw: object, item: dict[object, object]) -> MarketBar | None:
        try:
            timestamp = ensure_utc(datetime.fromisoformat(f"{timestamp_raw}T00:00:00"))
            open_raw = item["1. open"]
            high_raw = item["2. high"]
            low_raw = item["3. low"]
            close_raw = item["4. close"]
        except (KeyError, TypeError, ValueError):
            return None
        open_value = _float_or_none(open_raw)
        high_value = _float_or_none(high_raw)
        low_value = _float_or_none(low_raw)
        close_value = _float_or_none(close_raw)
        if open_value is None or high_value is None or low_value is None or close_value is None:
            return None
        return MarketBar(
            timestamp=timestamp,
            open=open_value,
            high=high_value,
            low=low_value,
            close=close_value,
            volume=None,
            source=self.name,
        )

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
            bar = self._parse_intraday_entry(timestamp_raw, item)
            if bar is None:
                continue
            bars.append(bar)
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
            bar = self._parse_daily_entry(timestamp_raw, item)
            if bar is None:
                continue
            bars.append(bar)
        bars.sort(key=lambda bar: bar.timestamp)
        return [bar for bar in bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]

    def _parse_numeric_series_payload(
        self,
        payload: dict[str, object],
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        data = payload.get("data")
        if not isinstance(data, list):
            return []

        bars: list[MarketBar] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            date_raw = str(item.get("date") or "").strip()
            value_raw = str(item.get("value") or "").strip()
            if not date_raw or not value_raw or value_raw == ".":
                continue
            try:
                timestamp = ensure_utc(datetime.fromisoformat(f"{date_raw}T00:00:00"))
                value = float(value_raw)
            except ValueError:
                continue
            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=value,
                    high=value,
                    low=value,
                    close=value,
                    volume=None,
                    source=self.name,
                ),
            )
        bars.sort(key=lambda bar: bar.timestamp)
        return [bar for bar in bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]

    async def fetch_bars(self, coin: Coin, interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        query = self._resolve_query(coin)
        if query is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")

        normalized_interval = normalize_interval(interval)
        if normalized_interval not in query.supported_intervals:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol} with interval {normalized_interval}.")

        if query.kind == "series":
            params: dict[str, HttpQueryValue] = {
                "function": str(query.function),
                "apikey": self.api_key,
            }
            if query.interval is not None:
                params["interval"] = query.interval
            if query.maturity is not None:
                params["maturity"] = query.maturity
            payload = await self._request_payload(params)
            return self._parse_numeric_series_payload(payload, start, end)

        if query.base_symbol is None or query.quote_symbol is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not define FX symbols for {coin.symbol}.")
        base_symbol, quote_symbol = query.base_symbol, query.quote_symbol

        if normalized_interval == "1d":
            payload = await self._request_payload(
                http_query_params(
                    function="FX_DAILY",
                    from_symbol=base_symbol,
                    to_symbol=quote_symbol,
                    outputsize="full",
                    apikey=self.api_key,
                )
            )
            return self._parse_daily_payload(payload, start, end)

        payload = await self._request_payload(
            http_query_params(
                function="FX_INTRADAY",
                from_symbol=base_symbol,
                to_symbol=quote_symbol,
                interval=ALPHA_VANTAGE_INTRADAY_INTERVALS[normalized_interval],
                outputsize="full",
                apikey=self.api_key,
            )
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


AlphaVantageForexMarketSource = AlphaVantageMarketSource

__all__ = [
    "ALPHA_VANTAGE_FOREX_PAIRS",
    "ALPHA_VANTAGE_SPECIAL_SERIES",
    "AlphaVantageForexMarketSource",
    "AlphaVantageMarketSource",
]
