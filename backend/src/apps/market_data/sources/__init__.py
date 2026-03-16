import asyncio
import math
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.apps.market_data.domain import ensure_utc, interval_delta, latest_completed_timestamp, normalize_interval
from src.apps.market_data.sources.alphavantage import AlphaVantageMarketSource
from src.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    MarketSourceError,
    RateLimitedMarketSourceError,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)
from src.apps.market_data.sources.binance import BinanceMarketSource
from src.apps.market_data.sources.coinbase import CoinbaseMarketSource
from src.apps.market_data.sources.eia import EiaEnergyMarketSource
from src.apps.market_data.sources.fred import FredMacroMarketSource
from src.apps.market_data.sources.kraken import KrakenMarketSource
from src.apps.market_data.sources.kucoin import KucoinMarketSource
from src.apps.market_data.sources.moex import MoexIndexMarketSource
from src.apps.market_data.sources.polygon import PolygonMarketSource
from src.apps.market_data.sources.rate_limits import get_rate_limit_manager
from src.apps.market_data.sources.stooq import StooqMarketSource
from src.apps.market_data.sources.twelvedata import TwelveDataMarketSource
from src.apps.market_data.sources.yfinance import YahooMarketSource

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


DEFAULT_PROVIDER_CHAIN_BY_ASSET_TYPE: dict[str, tuple[str, ...]] = {
    "crypto": ("binance", "kucoin", "kraken", "coinbase", "yahoo"),
    "index": ("moex", "stooq", "fred", "polygon", "twelvedata", "alphavantage", "yahoo"),
    "forex": ("polygon", "twelvedata", "alphavantage", "yahoo"),
    "metal": ("stooq", "yahoo", "twelvedata"),
    "energy": ("eia", "alphavantage", "yahoo"),
}


@dataclass(slots=True)
class MarketFetchResult:
    bars: list[MarketBar]
    completed: bool
    source_names: list[str]
    error: str | None = None
    retry_after_seconds: int | None = None


class MarketSourceCarousel:
    def __init__(self) -> None:
        self.sources: dict[str, BaseMarketSource] = {
            "binance": BinanceMarketSource(),
            "kucoin": KucoinMarketSource(),
            "kraken": KrakenMarketSource(),
            "coinbase": CoinbaseMarketSource(),
            "moex": MoexIndexMarketSource(),
            "eia": EiaEnergyMarketSource(),
            "fred": FredMacroMarketSource(),
            "polygon": PolygonMarketSource(),
            "stooq": StooqMarketSource(),
            "twelvedata": TwelveDataMarketSource(),
            "alphavantage": AlphaVantageMarketSource(),
            "yahoo": YahooMarketSource(),
        }
        self._cursor: dict[tuple[str, str], int] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        for source in self.sources.values():
            await source.close()

    def provider_names_for_coin(self, coin: Coin) -> list[str]:
        chain = list(DEFAULT_PROVIDER_CHAIN_BY_ASSET_TYPE.get(coin.asset_type, ("yahoo",)))
        normalized_preferred = (coin.source or "").strip().lower()
        if normalized_preferred and normalized_preferred != "default" and normalized_preferred in self.sources:
            if normalized_preferred in chain:
                chain = [normalized_preferred, *[source_name for source_name in chain if source_name != normalized_preferred]]
            else:
                chain = [normalized_preferred, *chain]
        return [
            source_name
            for source_name in chain
            if source_name in self.sources and self.sources[source_name].supports_coin_identity(coin)
        ]

    async def fetch_history_window(
        self,
        coin: Coin,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> MarketFetchResult:
        normalized_interval = normalize_interval(interval)
        provider_names = [
            name for name in self.provider_names_for_coin(coin) if self.sources[name].supports_coin(coin, normalized_interval)
        ]
        if not provider_names:
            return MarketFetchResult(
                bars=[],
                completed=False,
                source_names=[],
                error=f"No market source supports {coin.symbol} with interval {normalized_interval}.",
            )

        cursor_key = (coin.symbol, normalized_interval)
        async with self._lock:
            start_index = self._cursor.get(cursor_key, 0) % len(provider_names)
        current = ensure_utc(start)
        last_available = latest_completed_timestamp(normalized_interval, end + interval_delta(normalized_interval))
        attempts_without_progress = 0
        collected: dict[datetime, MarketBar] = {}
        last_error: str | None = None
        retry_after_seconds: int | None = None
        source_names_used: list[str] = []

        while current <= last_available:
            progress_made = False
            for offset in range(len(provider_names)):
                index = (start_index + offset) % len(provider_names)
                source_name = provider_names[index]
                source = self.sources[source_name]
                source_names_used.append(source_name)

                if await source.is_rate_limited():
                    cooldown_seconds = await get_rate_limit_manager().cooldown_seconds(source_name)
                    if cooldown_seconds > 0:
                        retry_after_seconds = max(retry_after_seconds or 0, max(math.ceil(cooldown_seconds), 1))
                    last_error = f"{source_name} is temporarily rate limited."
                    continue

                try:
                    request_end = min(
                        last_available,
                        current + interval_delta(normalized_interval) * (source.bars_per_request(normalized_interval) - 1),
                    )
                    bars = await source.fetch_bars(coin, normalized_interval, current, request_end)
                except RateLimitedMarketSourceError as exc:
                    retry_after_seconds = max(retry_after_seconds or 0, max(int(exc.retry_after_seconds), 1))
                    last_error = str(exc)
                    continue
                except UnsupportedMarketSourceQuery as exc:
                    last_error = str(exc)
                    continue
                except TemporaryMarketSourceError as exc:
                    last_error = str(exc)
                    continue
                except MarketSourceError as exc:
                    last_error = str(exc)
                    continue

                if not bars:
                    if collected and request_end >= last_available and source.allows_terminal_gap(coin):
                        async with self._lock:
                            self._cursor[cursor_key] = (index + 1) % len(provider_names)
                        return MarketFetchResult(
                            bars=sorted(collected.values(), key=lambda item: item.timestamp),
                            completed=True,
                            source_names=source_names_used,
                            error=None,
                        )
                    last_error = f"{source_name} returned no bars for {coin.symbol}."
                    continue
                next_current = current
                for bar in bars:
                    bar_timestamp = ensure_utc(bar.timestamp)
                    if bar_timestamp < current or bar_timestamp > last_available:
                        continue
                    collected[bar_timestamp] = bar
                    next_current = max(next_current, bar_timestamp + interval_delta(normalized_interval))

                if next_current <= current:
                    last_error = f"{source_name} did not advance cursor for {coin.symbol}."
                    continue

                current = next_current
                attempts_without_progress = 0
                progress_made = True
                async with self._lock:
                    self._cursor[cursor_key] = (index + 1) % len(provider_names)
                break

            if progress_made:
                continue

            attempts_without_progress += 1
            start_index = (start_index + 1) % len(provider_names)
            if attempts_without_progress >= 3:
                return MarketFetchResult(
                    bars=sorted(collected.values(), key=lambda item: item.timestamp),
                    completed=False,
                    source_names=source_names_used,
                    error=last_error or f"Exhausted market source carousel for {coin.symbol}.",
                    retry_after_seconds=retry_after_seconds,
                )

        return MarketFetchResult(
            bars=sorted(collected.values(), key=lambda item: item.timestamp),
            completed=True,
            source_names=source_names_used,
            error=None,
        )


_carousel: MarketSourceCarousel | None = None


def get_market_source_carousel() -> MarketSourceCarousel:
    global _carousel
    if _carousel is None:
        _carousel = MarketSourceCarousel()
    return _carousel
