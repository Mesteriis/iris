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
from iris.apps.market_data.sources.rate_limits import HttpQueryValue

if TYPE_CHECKING:
    from iris.apps.market_data.models import Coin


MOEX_SYMBOLS: dict[str, str] = {
    "IMOEX": "IMOEX",
    "RTSI": "RTSI",
}

MOEX_INTERVALS: dict[str, int] = {
    "1h": 60,
    "4h": 60,
    "1d": 24,
}

MOEX_PAGE_SIZE = 500


class MoexIndexMarketSource(BaseMarketSource):
    name = "moex"
    asset_types: ClassVar[set[str]] = {"index"}
    supported_intervals: ClassVar[set[str]] = {"1h", "4h", "1d"}
    base_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities"

    def get_symbol(self, coin: Coin) -> str | None:
        return self.resolve_provider_symbol(coin.symbol, fallback=MOEX_SYMBOLS.get(coin.symbol))

    def bars_per_request(self, interval: str) -> int:
        return MOEX_PAGE_SIZE

    def allows_terminal_gap(self, coin: Coin) -> bool:
        del coin
        return True

    async def fetch_bars(self, coin: Coin, interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        symbol = self.get_symbol(coin)
        if symbol is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")

        normalized_interval = normalize_interval(interval)
        moex_interval = MOEX_INTERVALS.get(normalized_interval)
        if moex_interval is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol} on {interval}.")

        url = f"{self.base_url}/{symbol}/candles.json"
        params: dict[str, HttpQueryValue] = {
            "from": ensure_utc(start).date().isoformat(),
            "till": ensure_utc(end).date().isoformat(),
            "interval": moex_interval,
        }

        raw_bars: list[MarketBar] = []
        page_start = 0
        while True:
            try:
                page_params: dict[str, HttpQueryValue] = dict(params)
                page_params["start"] = page_start
                response = await self.request(url, params=page_params)
                if response.status_code in {400, 404}:
                    raise UnsupportedMarketSourceQuery(f"{self.name} rejected params for {coin.symbol}.")
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError as exc:
                raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

            data = (payload.get("candles") or {}).get("data") or []
            if not data:
                break

            for item in data:
                begin_raw = item[6]
                open_raw, close_raw, high_raw, low_raw, _, volume_raw = item[:6]
                if begin_raw is None or open_raw is None or close_raw is None:
                    continue
                timestamp = datetime.fromisoformat(begin_raw).replace(tzinfo=ensure_utc(start).tzinfo)
                raw_bars.append(
                    MarketBar(
                        timestamp=timestamp,
                        open=float(open_raw),
                        high=float(high_raw) if high_raw is not None else float(open_raw),
                        low=float(low_raw) if low_raw is not None else float(open_raw),
                        close=float(close_raw),
                        volume=float(volume_raw) if volume_raw is not None else None,
                        source=self.name,
                    )
                )

            if len(data) < MOEX_PAGE_SIZE:
                break
            page_start += MOEX_PAGE_SIZE

        raw_bars.sort(key=lambda bar: bar.timestamp)
        if normalized_interval == "4h":
            return self._resample_four_hour_bars(raw_bars, start, end)
        return [bar for bar in raw_bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]

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
