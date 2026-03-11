from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from app.apps.market_data.domain import ensure_utc, interval_delta, normalize_interval
from app.apps.market_data.sources.rate_limits import (
    get_rate_limit_manager,
    get_rate_limit_policy,
    rate_limited_get,
)

if TYPE_CHECKING:
    from app.apps.market_data.models import Coin


class MarketSourceError(Exception):
    pass


class UnsupportedMarketSourceQuery(MarketSourceError):
    pass


class TemporaryMarketSourceError(MarketSourceError):
    pass


class RateLimitedMarketSourceError(MarketSourceError):
    def __init__(self, source: str, retry_after_seconds: int, message: str) -> None:
        super().__init__(message)
        self.source = source
        self.retry_after_seconds = retry_after_seconds


@dataclass(slots=True, frozen=True)
class MarketBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    source: str


class BaseMarketSource:
    name = "base"
    asset_types: set[str] = set()
    supported_intervals: set[str] = set()
    rate_limit_status_codes: set[int] = {429}

    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=15.0),
            headers={
                "User-Agent": "IRIS/0.1 market-sync",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def supports_coin(self, coin: "Coin", interval: str) -> bool:
        normalized_interval = normalize_interval(interval)
        return (
            coin.asset_type in self.asset_types
            and normalized_interval in self.supported_intervals
            and self.get_symbol(coin) is not None
        )

    def get_symbol(self, coin: "Coin") -> str | None:
        raise NotImplementedError

    def fetch_bars(
        self,
        coin: "Coin",
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        raise NotImplementedError

    def is_rate_limited(self) -> bool:
        return get_rate_limit_manager().is_rate_limited(self.name)

    def set_rate_limit(self, seconds: int) -> None:
        get_rate_limit_manager().set_cooldown(self.name, seconds)

    def clear_rate_limit(self) -> None:
        get_rate_limit_manager().clear_cooldown(self.name)

    def bars_per_request(self, interval: str) -> int:
        raise NotImplementedError

    def allows_terminal_gap(self, coin: "Coin") -> bool:
        del coin
        return False

    def _limit_for_range(self, interval: str, start: datetime, end: datetime) -> int:
        normalized_start = ensure_utc(start)
        normalized_end = ensure_utc(end)
        delta = interval_delta(interval)
        return int((normalized_end - normalized_start) / delta) + 1

    def request(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        rate_limit_statuses: set[int] | None = None,
        fallback_retry_after_seconds: int | None = None,
        cost: int | None = None,
    ) -> httpx.Response:
        try:
            return rate_limited_get(
                self.name,
                self.client,
                url,
                params=params,
                headers=headers,
                rate_limit_statuses=rate_limit_statuses or self.rate_limit_status_codes,
                fallback_retry_after_seconds=fallback_retry_after_seconds,
                cost=cost,
            )
        except RateLimitedMarketSourceError:
            raise
        except httpx.HTTPError as exc:
            raise TemporaryMarketSourceError(f"{self.name} transport error: {exc}") from exc

    def raise_rate_limited(
        self,
        *,
        retry_after_seconds: int | None = None,
        message: str | None = None,
    ) -> None:
        policy = get_rate_limit_policy(self.name)
        delay = max(int(retry_after_seconds or policy.fallback_retry_after_seconds), 1)
        self.set_rate_limit(delay)
        raise RateLimitedMarketSourceError(self.name, delay, message or f"{self.name} rate limited")

    @staticmethod
    def _retry_after(response: httpx.Response, fallback: int) -> int:
        raw = response.headers.get("Retry-After")
        if raw and raw.isdigit():
            return int(raw)
        kucoin_reset = response.headers.get("gw-ratelimit-reset")
        if kucoin_reset and kucoin_reset.isdigit():
            return max(int(kucoin_reset) // 1000, 1)
        return max(fallback, 1)
