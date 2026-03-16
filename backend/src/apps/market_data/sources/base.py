from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import TYPE_CHECKING, ClassVar

import httpx

from src.apps.market_data.domain import ensure_utc, interval_delta, normalize_interval
from src.apps.market_data.sources.proxy_registry import get_free_proxy_registry
from src.apps.market_data.sources.rate_limits import (
    HttpQueryParams,
    HttpQueryValue,
    get_rate_limit_manager,
    get_rate_limit_policy,
    rate_limited_get,
)
from src.core.settings import get_settings

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


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


def http_query_params(**params: HttpQueryValue) -> dict[str, HttpQueryValue]:
    return params


class BaseMarketSource:
    name = "base"
    asset_types: ClassVar[set[str]] = set()
    supported_intervals: ClassVar[set[str]] = set()
    rate_limit_status_codes: ClassVar[set[int]] = {429}
    proxy_pool_mode = "off"

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=15.0),
            headers={
                "User-Agent": "IRIS/0.1 market-sync",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self.client.aclose()

    def resolve_provider_symbol(
        self,
        canonical_symbol: str,
        *,
        fallback: str | None = None,
    ) -> str | None:
        from src.apps.market_data.sources.source_capability_registry import get_market_source_capability_registry

        return get_market_source_capability_registry().resolve_provider_symbol(
            self.name,
            canonical_symbol,
            fallback=fallback,
        )

    def supports_canonical_symbol(
        self,
        canonical_symbol: str,
        *,
        fallback: bool = False,
    ) -> bool:
        from src.apps.market_data.sources.source_capability_registry import get_market_source_capability_registry

        return get_market_source_capability_registry().supports_canonical_symbol(
            self.name,
            canonical_symbol,
            fallback=fallback,
        )

    def supports_coin_identity(self, coin: Coin) -> bool:
        return coin.asset_type in self.asset_types and self.get_symbol(coin) is not None

    def supports_coin(self, coin: Coin, interval: str) -> bool:
        normalized_interval = normalize_interval(interval)
        return self.supports_coin_identity(coin) and normalized_interval in self.supported_intervals

    def get_symbol(self, coin: Coin) -> str | None:
        raise NotImplementedError

    async def fetch_bars(
        self,
        coin: Coin,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketBar]:
        raise NotImplementedError

    async def is_rate_limited(self) -> bool:
        manager = get_rate_limit_manager()
        if not await manager.is_rate_limited(self.name):
            return False
        if self.proxy_pool_mode == "off":
            return True
        return not await get_free_proxy_registry().has_available_proxy()

    async def set_rate_limit(self, seconds: int) -> None:
        await get_rate_limit_manager().set_cooldown(self.name, seconds)

    async def clear_rate_limit(self) -> None:
        await get_rate_limit_manager().clear_cooldown(self.name)

    def bars_per_request(self, interval: str) -> int:
        raise NotImplementedError

    def allows_terminal_gap(self, coin: Coin) -> bool:
        del coin
        return False

    def _limit_for_range(self, interval: str, start: datetime, end: datetime) -> int:
        normalized_start = ensure_utc(start)
        normalized_end = ensure_utc(end)
        delta = interval_delta(interval)
        return int((normalized_end - normalized_start) / delta) + 1

    async def request(
        self,
        url: str,
        *,
        params: HttpQueryParams | None = None,
        headers: dict[str, str] | None = None,
        rate_limit_statuses: set[int] | None = None,
        fallback_retry_after_seconds: int | None = None,
        cost: int | None = None,
    ) -> httpx.Response:
        merged_headers = dict(self.client.headers)
        if headers:
            merged_headers.update(headers)
        try:
            if self.proxy_pool_mode == "off":
                return await self._request_direct(
                    url,
                    params=params,
                    headers=merged_headers,
                    rate_limit_statuses=rate_limit_statuses,
                    fallback_retry_after_seconds=fallback_retry_after_seconds,
                    cost=cost,
                )

            settings = get_settings()
            registry = get_free_proxy_registry()
            max_proxy_attempts = max(settings.free_proxy_pool_max_proxy_attempts, 1)
            proxy_urls = await registry.get_best_proxies(limit=max_proxy_attempts)
            direct_cooldown = await get_rate_limit_manager().cooldown_seconds(self.name)
            direct_rate_limited = direct_cooldown > 0

            last_rate_limited: RateLimitedMarketSourceError | None = None
            last_transport_error: httpx.HTTPError | None = None
            attempted_direct = False

            if self.proxy_pool_mode == "fallback" and not direct_rate_limited:
                attempted_direct = True
                try:
                    return await self._request_direct(
                        url,
                        params=params,
                        headers=merged_headers,
                        rate_limit_statuses=rate_limit_statuses,
                        fallback_retry_after_seconds=fallback_retry_after_seconds,
                        cost=cost,
                    )
                except RateLimitedMarketSourceError as exc:
                    last_rate_limited = exc
                except httpx.HTTPError as exc:
                    last_transport_error = exc

            for proxy_url in proxy_urls:
                try:
                    return await self._request_via_proxy(
                        proxy_url,
                        url,
                        params=params,
                        headers=merged_headers,
                        rate_limit_statuses=rate_limit_statuses,
                        fallback_retry_after_seconds=fallback_retry_after_seconds,
                        cost=cost,
                    )
                except RateLimitedMarketSourceError as exc:
                    last_rate_limited = exc
                    continue
                except httpx.HTTPError as exc:
                    last_transport_error = exc
                    continue

            if not direct_rate_limited and not attempted_direct:
                return await self._request_direct(
                    url,
                    params=params,
                    headers=merged_headers,
                    rate_limit_statuses=rate_limit_statuses,
                    fallback_retry_after_seconds=fallback_retry_after_seconds,
                    cost=cost,
                )
            if last_rate_limited is not None:
                raise last_rate_limited
            if last_transport_error is not None:
                raise last_transport_error
            raise RateLimitedMarketSourceError(
                self.name,
                max(int(direct_cooldown), 1),
                f"{self.name} direct path is temporarily rate limited",
            )
        except RateLimitedMarketSourceError:
            raise
        except httpx.HTTPError as exc:
            raise TemporaryMarketSourceError(f"{self.name} transport error: {exc}") from exc

    async def _request_direct(
        self,
        url: str,
        *,
        params: HttpQueryParams | None,
        headers: dict[str, str],
        rate_limit_statuses: set[int] | None,
        fallback_retry_after_seconds: int | None,
        cost: int | None,
    ) -> httpx.Response:
        return await rate_limited_get(
            self.name,
            self.client,
            url,
            params=params,
            headers=headers,
            rate_limit_statuses=rate_limit_statuses or self.rate_limit_status_codes,
            fallback_retry_after_seconds=fallback_retry_after_seconds,
            cost=cost,
        )

    async def _request_via_proxy(
        self,
        proxy_url: str,
        url: str,
        *,
        params: HttpQueryParams | None,
        headers: dict[str, str],
        rate_limit_statuses: set[int] | None,
        fallback_retry_after_seconds: int | None,
        cost: int | None,
    ) -> httpx.Response:
        proxy_client = httpx.AsyncClient(
            timeout=self.client.timeout,
            headers=dict(self.client.headers),
            follow_redirects=True,
            proxy=proxy_url,
            trust_env=False,
        )
        registry = get_free_proxy_registry()
        started_at = perf_counter()
        try:
            response = await rate_limited_get(
                self.name,
                proxy_client,
                url,
                params=params,
                headers=headers,
                rate_limit_statuses=rate_limit_statuses or self.rate_limit_status_codes,
                fallback_retry_after_seconds=fallback_retry_after_seconds,
                cost=cost,
                rate_limit_identity=f"{self.name}:proxy:{proxy_url}",
            )
        except RateLimitedMarketSourceError as exc:
            await registry.record_rate_limited(proxy_url, retry_after_seconds=exc.retry_after_seconds)
            raise
        except httpx.HTTPError as exc:
            await registry.record_failure(proxy_url, reason=f"{self.name} proxy transport error: {exc}", cooldown_seconds=300)
            raise
        else:
            await registry.record_success(proxy_url, latency_ms=(perf_counter() - started_at) * 1000)
            return response
        finally:
            await proxy_client.aclose()

    async def raise_rate_limited(
        self,
        *,
        retry_after_seconds: int | None = None,
        message: str | None = None,
    ) -> None:
        policy = get_rate_limit_policy(self.name)
        delay = max(int(retry_after_seconds or policy.fallback_retry_after_seconds), 1)
        await self.set_rate_limit(delay)
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
