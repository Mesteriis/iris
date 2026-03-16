from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import httpx

from src.apps.market_data.domain import ensure_utc, normalize_interval
from src.apps.market_data.sources.base import (
    BaseMarketSource,
    MarketBar,
    TemporaryMarketSourceError,
    UnsupportedMarketSourceQuery,
)
from src.core.settings import get_settings

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


EIA_SERIES_IDS: dict[str, str] = {
    "BRENTUSD": "PET.RBRTE.D",
    "NATGASUSD": "NG.RNGWHHD.D",
    "WTIUSD": "PET.RWTC.D",
}


class EiaEnergyMarketSource(BaseMarketSource):
    name = "eia"
    asset_types: ClassVar[set[str]] = {"energy"}
    supported_intervals: ClassVar[set[str]] = {"1d"}
    base_url = "https://api.eia.gov/v2/seriesid"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_settings().eia_api_key.strip()

    def supports_coin(self, coin: Coin, interval: str) -> bool:
        if not self.api_key:
            return False
        return super().supports_coin(coin, interval)

    def get_symbol(self, coin: Coin) -> str | None:
        return self.resolve_provider_symbol(coin.symbol, fallback=EIA_SERIES_IDS.get(coin.symbol))

    def bars_per_request(self, interval: str) -> int:
        del interval
        return 100_000

    def allows_terminal_gap(self, coin: Coin) -> bool:
        del coin
        return True

    async def fetch_bars(self, coin: Coin, interval: str, start: datetime, end: datetime) -> list[MarketBar]:
        series_id = self.get_symbol(coin)
        if series_id is None:
            raise UnsupportedMarketSourceQuery(f"{self.name} does not support {coin.symbol}.")
        if normalize_interval(interval) != "1d":
            raise UnsupportedMarketSourceQuery(f"{self.name} only supports daily history for {coin.symbol}.")

        try:
            response = await self.request(
                f"{self.base_url}/{series_id}",
                params={
                    "api_key": self.api_key,
                    "out": "json",
                },
                fallback_retry_after_seconds=60,
            )
            if response.status_code in {400, 401, 403, 404}:
                try:
                    payload = response.json()
                except Exception:
                    payload = {}
                message = str(payload.get("error") or payload.get("message") or f"{self.name} rejected params for {coin.symbol}.")
                raise UnsupportedMarketSourceQuery(message)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise TemporaryMarketSourceError(f"{self.name} http error: {exc.response.status_code}") from exc

        if not isinstance(payload, dict):
            raise TemporaryMarketSourceError(f"{self.name} returned an unexpected payload for {coin.symbol}.")
        if payload.get("error") or payload.get("message"):
            raise UnsupportedMarketSourceQuery(str(payload.get("error") or payload.get("message")))
        response_payload = payload.get("response")
        if not isinstance(response_payload, dict):
            raise TemporaryMarketSourceError(f"{self.name} returned an unexpected response envelope for {coin.symbol}.")

        bars: list[MarketBar] = []
        for item in response_payload.get("data", []) or []:
            if not isinstance(item, dict):
                continue
            period_raw = str(item.get("period") or "").strip()
            value_raw = item.get("value")
            if not period_raw or value_raw in {None, "", "."}:
                continue
            try:
                timestamp = ensure_utc(datetime.fromisoformat(f"{period_raw}T00:00:00"))
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
                )
            )

        bars.sort(key=lambda bar: bar.timestamp)
        return [bar for bar in bars if ensure_utc(start) <= bar.timestamp <= ensure_utc(end)]
