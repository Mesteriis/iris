import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_structure.constants import (
    DEFAULT_BINANCE_USDM_API_BASE_URL,
    DEFAULT_BYBIT_API_BASE_URL,
    DEFAULT_MARKET_STRUCTURE_POLL_LIMIT,
    MARKET_STRUCTURE_PLUGIN_BINANCE_USDM,
    MARKET_STRUCTURE_PLUGIN_BYBIT_DERIVATIVES,
    MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
)
from src.apps.market_structure.exceptions import (
    InvalidMarketStructureSourceConfigurationError,
    UnsupportedMarketStructurePluginError,
)

if TYPE_CHECKING:
    from src.apps.market_structure.models import MarketStructureSource


@dataclass(frozen=True, slots=True)
class MarketStructurePluginDescriptor:
    name: str
    display_name: str
    description: str
    auth_mode: str
    supported: bool
    supports_polling: bool = True
    supports_manual_ingest: bool = False
    required_credentials: tuple[str, ...] = ()
    required_settings: tuple[str, ...] = ()
    runtime_dependencies: tuple[str, ...] = ()
    unsupported_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FetchedMarketStructureSnapshot:
    venue: str
    timestamp: datetime
    last_price: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    basis: float | None = None
    liquidations_long: float | None = None
    liquidations_short: float | None = None
    volume: float | None = None
    payload_json: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MarketStructureFetchResult:
    snapshots: list[FetchedMarketStructureSnapshot]
    next_cursor: dict[str, Any]


class MarketStructureSourcePlugin(ABC):
    descriptor: MarketStructurePluginDescriptor

    def __init__(self, source: MarketStructureSource) -> None:
        self.source = source
        self.credentials = dict(source.credentials_json or {})
        self.settings = dict(source.settings_json or {})

    @classmethod
    def validate_configuration(
        cls,
        *,
        credentials: dict[str, Any],
        settings: dict[str, Any],
    ) -> None:
        if not cls.descriptor.supported:
            raise UnsupportedMarketStructurePluginError(
                cls.descriptor.unsupported_reason or f"Plugin '{cls.descriptor.name}' is unsupported."
            )
        missing_credentials = [
            field
            for field in cls.descriptor.required_credentials
            if credentials.get(field) in (None, "")
        ]
        missing_settings = [
            field
            for field in cls.descriptor.required_settings
            if settings.get(field) in (None, "")
        ]
        if missing_credentials or missing_settings:
            missing = ", ".join(
                [*(f"credentials.{item}" for item in missing_credentials), *(f"settings.{item}" for item in missing_settings)]
            )
            raise InvalidMarketStructureSourceConfigurationError(f"Missing required configuration fields: {missing}.")

    @abstractmethod
    async def fetch_snapshots(
        self,
        *,
        cursor: dict[str, Any],
        limit: int = DEFAULT_MARKET_STRUCTURE_POLL_LIMIT,
    ) -> MarketStructureFetchResult:
        raise NotImplementedError


_REGISTRY: dict[str, type[MarketStructureSourcePlugin]] = {}


def register_market_structure_plugin(name: str, plugin_cls: type[MarketStructureSourcePlugin]) -> None:
    _REGISTRY[name.strip().lower()] = plugin_cls


def get_market_structure_plugin(name: str) -> type[MarketStructureSourcePlugin] | None:
    return _REGISTRY.get(name.strip().lower())


def list_registered_market_structure_plugins() -> dict[str, type[MarketStructureSourcePlugin]]:
    return dict(sorted(_REGISTRY.items()))


def create_market_structure_plugin(source: MarketStructureSource) -> MarketStructureSourcePlugin:
    plugin_cls = get_market_structure_plugin(source.plugin_name)
    if plugin_cls is None:
        raise ValueError(f"Unsupported market structure plugin '{source.plugin_name}'.")
    return plugin_cls(source)


def _float_or_none(value: object) -> float | None:
    if value in (None, "", "None"):
        return None
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


def _timestamp_millis_value(value: object) -> float | None:
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


def _computed_basis(mark_price: float | None, index_price: float | None) -> float | None:
    if mark_price is None or index_price is None or index_price == 0.0:
        return None
    return (mark_price - index_price) / index_price


def _timestamp_from_millis(value: object) -> datetime:
    if value in (None, ""):
        return utc_now()
    millis = _timestamp_millis_value(value)
    if millis is None:
        return utc_now()
    return ensure_utc(datetime.fromtimestamp(millis / 1000.0, tz=UTC))


class BinanceUsdMarketStructurePlugin(MarketStructureSourcePlugin):
    descriptor = MarketStructurePluginDescriptor(
        name=MARKET_STRUCTURE_PLUGIN_BINANCE_USDM,
        display_name="Binance USD-M Futures",
        description="Poll funding, mark/index price and open interest from Binance USD-M Futures.",
        auth_mode="public",
        supported=True,
        required_settings=("coin_symbol", "market_symbol", "timeframe"),
    )

    async def fetch_snapshots(
        self,
        *,
        cursor: dict[str, Any],
        limit: int = DEFAULT_MARKET_STRUCTURE_POLL_LIMIT,
    ) -> MarketStructureFetchResult:
        del cursor
        del limit
        market_symbol = str(self.settings["market_symbol"]).strip().upper()
        venue = str(self.settings.get("venue") or "binance_usdm").strip().lower()
        base_url = str(self.settings.get("api_base_url") or DEFAULT_BINANCE_USDM_API_BASE_URL).rstrip("/")

        async with httpx.AsyncClient(timeout=20.0) as client:
            premium_response, open_interest_response = await asyncio.gather(
                client.get(f"{base_url}/fapi/v1/premiumIndex", params={"symbol": market_symbol}),
                client.get(f"{base_url}/fapi/v1/openInterest", params={"symbol": market_symbol}),
            )
            premium_response.raise_for_status()
            open_interest_response.raise_for_status()

        premium_payload = premium_response.json()
        open_interest_payload = open_interest_response.json()
        timestamp = _timestamp_from_millis(
            premium_payload.get("time") or open_interest_payload.get("time")
        )
        mark_price = _float_or_none(premium_payload.get("markPrice"))
        index_price = _float_or_none(premium_payload.get("indexPrice"))
        basis = _computed_basis(mark_price, index_price)
        snapshot = FetchedMarketStructureSnapshot(
            venue=venue,
            timestamp=timestamp,
            last_price=mark_price,
            mark_price=mark_price,
            index_price=index_price,
            funding_rate=_float_or_none(premium_payload.get("lastFundingRate")),
            open_interest=_float_or_none(open_interest_payload.get("openInterest")),
            basis=basis,
            volume=None,
            payload_json={
                "premium_index": premium_payload,
                "open_interest": open_interest_payload,
            },
        )
        return MarketStructureFetchResult(snapshots=[snapshot], next_cursor={})


class BybitDerivativesMarketStructurePlugin(MarketStructureSourcePlugin):
    descriptor = MarketStructurePluginDescriptor(
        name=MARKET_STRUCTURE_PLUGIN_BYBIT_DERIVATIVES,
        display_name="Bybit Derivatives",
        description="Poll derivatives tickers from Bybit V5 for funding, mark/index price and open interest.",
        auth_mode="public",
        supported=True,
        required_settings=("coin_symbol", "market_symbol", "timeframe"),
    )

    async def fetch_snapshots(
        self,
        *,
        cursor: dict[str, Any],
        limit: int = DEFAULT_MARKET_STRUCTURE_POLL_LIMIT,
    ) -> MarketStructureFetchResult:
        del cursor
        del limit
        market_symbol = str(self.settings["market_symbol"]).strip().upper()
        venue = str(self.settings.get("venue") or "bybit_derivatives").strip().lower()
        category = str(self.settings.get("category") or "linear").strip().lower()
        base_url = str(self.settings.get("api_base_url") or DEFAULT_BYBIT_API_BASE_URL).rstrip("/")

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{base_url}/v5/market/tickers",
                params={"category": category, "symbol": market_symbol},
            )
            response.raise_for_status()
        payload = response.json()
        rows = ((payload.get("result") or {}).get("list") or [])
        if not rows:
            return MarketStructureFetchResult(snapshots=[], next_cursor={})
        row = rows[0]
        timestamp = _timestamp_from_millis(payload.get("time"))
        last_price = _float_or_none(row.get("lastPrice"))
        mark_price = _float_or_none(row.get("markPrice"))
        index_price = _float_or_none(row.get("indexPrice"))
        basis = _float_or_none(row.get("basis"))
        if basis is None:
            basis = _computed_basis(mark_price, index_price)
        snapshot = FetchedMarketStructureSnapshot(
            venue=venue,
            timestamp=timestamp,
            last_price=last_price,
            mark_price=mark_price,
            index_price=index_price,
            funding_rate=_float_or_none(row.get("fundingRate")),
            open_interest=_float_or_none(row.get("openInterest")),
            basis=basis,
            volume=_float_or_none(row.get("volume24h")),
            payload_json=payload,
        )
        return MarketStructureFetchResult(snapshots=[snapshot], next_cursor={})


class ManualPushMarketStructurePlugin(MarketStructureSourcePlugin):
    descriptor = MarketStructurePluginDescriptor(
        name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
        display_name="Manual Push",
        description="Accept market structure snapshots pushed from an external collector or webhook.",
        auth_mode="push",
        supported=True,
        supports_polling=False,
        supports_manual_ingest=True,
        required_settings=("coin_symbol", "timeframe", "venue"),
    )

    async def fetch_snapshots(
        self,
        *,
        cursor: dict[str, Any],
        limit: int = DEFAULT_MARKET_STRUCTURE_POLL_LIMIT,
    ) -> MarketStructureFetchResult:
        del cursor
        del limit
        return MarketStructureFetchResult(snapshots=[], next_cursor={})


register_market_structure_plugin(MARKET_STRUCTURE_PLUGIN_BINANCE_USDM, BinanceUsdMarketStructurePlugin)
register_market_structure_plugin(MARKET_STRUCTURE_PLUGIN_BYBIT_DERIVATIVES, BybitDerivativesMarketStructurePlugin)
register_market_structure_plugin(MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH, ManualPushMarketStructurePlugin)
