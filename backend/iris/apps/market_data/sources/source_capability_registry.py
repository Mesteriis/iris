from __future__ import annotations

import asyncio
import csv
import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import StringIO
from itertools import product
from threading import Lock
from typing import Any, Protocol

import httpx

from iris.apps.market_data.sources.alphavantage import (
    ALPHA_VANTAGE_FOREX_PAIRS,
    ALPHA_VANTAGE_SPECIAL_SERIES,
    AlphaVantageSeriesSpec,
)
from iris.apps.market_data.sources.eia import EIA_SERIES_IDS
from iris.apps.market_data.sources.fred import FRED_SERIES_IDS
from iris.apps.market_data.sources.polygon import POLYGON_SYMBOLS
from iris.apps.market_data.sources.stooq import STOOQ_SYMBOLS
from iris.apps.market_data.sources.twelvedata import TWELVE_DATA_SYMBOL_CANDIDATES
from iris.apps.market_data.sources.yfinance import YAHOO_SYMBOLS
from iris.core.settings import get_settings
from iris.runtime.orchestration.locks import get_async_lock_redis

LOGGER = logging.getLogger(__name__)
REDIS_KEY = "iris:market_data:source_capability_registry:v1"
HttpQueryScalar = str | int | float | bool | None
HttpQueryValue = HttpQueryScalar | Sequence[HttpQueryScalar]
HttpQueryParams = Mapping[str, HttpQueryValue]
USD_QUOTES = ("USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP", "USDS", "PYUSD")
FIAT_OR_STABLE_TOKENS = {
    "AED",
    "ARS",
    "AUD",
    "BGN",
    "BRL",
    "CAD",
    "CHF",
    "CNY",
    "CZK",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "HUF",
    "IDR",
    "ILS",
    "INR",
    "JPY",
    "KRW",
    "MAD",
    "MXN",
    "MYR",
    "NGN",
    "NOK",
    "NZD",
    "PEN",
    "PHP",
    "PLN",
    "RON",
    "RUB",
    "SAR",
    "SEK",
    "SGD",
    "THB",
    "TRY",
    "UAH",
    "USD",
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "TUSD",
    "USDP",
    "USDS",
    "PYUSD",
    "VND",
    "ZAR",
}
BASE_ALIASES = {
    "XBT": "BTC",
    "XDG": "DOGE",
    "XETH": "ETH",
    "XXBT": "BTC",
    "XBT.M": "BTC",
}
QUOTE_ALIASES = {
    "ZUSD": "USD",
    "ZEUR": "EUR",
    "ZGBP": "GBP",
    "ZJPY": "JPY",
    "ZCAD": "CAD",
    "ZAUD": "AUD",
    "ZCHF": "CHF",
}
QUOTE_PRIORITY = {
    "USD": 0,
    "USDT": 1,
    "USDC": 2,
    "BUSD": 3,
    "FDUSD": 4,
    "TUSD": 5,
    "USDP": 6,
    "USDS": 7,
    "PYUSD": 8,
}
EXCHANGE_STABLE_PRIORITY = {
    "USDT": 0,
    "USDC": 1,
    "FDUSD": 2,
    "BUSD": 3,
    "TUSD": 4,
    "USDP": 5,
    "USDS": 6,
    "PYUSD": 7,
    "USD": 8,
}
POLYGON_REVERSE_ALIASES = {provider_symbol: canonical_symbol for canonical_symbol, provider_symbol in POLYGON_SYMBOLS.items()}
STOOQ_REVERSE_ALIASES = {provider_symbol: canonical_symbol for canonical_symbol, provider_symbol in STOOQ_SYMBOLS.items()}
TWELVE_DATA_REVERSE_ALIASES = {
    provider_symbol: canonical_symbol
    for canonical_symbol, provider_symbols in TWELVE_DATA_SYMBOL_CANDIDATES.items()
    for provider_symbol in provider_symbols
}
YAHOO_REVERSE_ALIASES = {provider_symbol: canonical_symbol for canonical_symbol, provider_symbol in YAHOO_SYMBOLS.items()}
ALPHA_VANTAGE_REVERSE_ALIASES = {
    f"{base_symbol}{quote_symbol}": canonical_symbol
    for canonical_symbol, (base_symbol, quote_symbol) in ALPHA_VANTAGE_FOREX_PAIRS.items()
}
EIA_REVERSE_ALIASES = {provider_symbol: canonical_symbol for canonical_symbol, provider_symbol in EIA_SERIES_IDS.items()}
FRED_REVERSE_ALIASES = {provider_symbol: canonical_symbol for canonical_symbol, provider_symbol in FRED_SERIES_IDS.items()}


class _CapabilitySettings(Protocol):
    polygon_api_key: str
    twelve_data_api_key: str
    alpha_vantage_api_key: str
    fred_api_key: str
    eia_api_key: str


type _Discoverer = Callable[[httpx.AsyncClient, _CapabilitySettings], Awaitable[SourceCapabilitySnapshot]]


def _serialize_timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _sanitize_request_url(value: httpx.URL | None) -> str | None:
    if value is None:
        return None
    try:
        return str(value.copy_with(query=None))
    except Exception:  # pragma: no cover - defensive fallback
        return str(value).split("?", 1)[0]


def _classify_discovery_error(exc: Exception) -> tuple[str, dict[str, object]]:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = int(exc.response.status_code)
        context: dict[str, object] = {
            "status_code": status_code,
            "url": _sanitize_request_url(exc.request.url),
        }
        if status_code == 429:
            return "upstream rate limited (429)", context
        return f"upstream http error ({status_code})", context
    if isinstance(exc, httpx.HTTPError):
        return (
            "upstream transport error",
            {
                "error_type": exc.__class__.__name__,
            },
        )
    return str(exc), {}


def _normalize_symbol_token(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]", "", value.strip().upper())
    return BASE_ALIASES.get(normalized, QUOTE_ALIASES.get(normalized, normalized))


def _normalize_crypto_quote(value: str) -> str:
    quote = QUOTE_ALIASES.get(value.strip().upper(), value.strip().upper())
    if quote in USD_QUOTES:
        return "USD"
    return quote


def _canonicalize_crypto_pair(base_symbol: str, quote_symbol: str) -> str:
    base = _normalize_symbol_token(base_symbol)
    quote = _normalize_crypto_quote(quote_symbol)
    return f"{base}{quote}"


def _canonicalize_forex_pair(base_symbol: str, quote_symbol: str) -> str:
    return f"{_normalize_symbol_token(base_symbol)}{_normalize_symbol_token(quote_symbol)}"


def _canonicalize_generic_symbol(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.strip().upper().replace("C:", "").replace("I:", "").replace("^", ""))


def _is_supported_crypto_base_symbol(base_symbol: str) -> bool:
    normalized_base = _normalize_symbol_token(base_symbol)
    return bool(normalized_base) and normalized_base not in FIAT_OR_STABLE_TOKENS


def _upsert_mapping(
    canonical_to_provider: dict[str, str],
    provider_to_canonical: dict[str, str],
    canonical_symbol: str | None,
    provider_symbol: str,
    *,
    priority: int = 100,
    priorities: dict[str, int] | None = None,
) -> None:
    normalized_provider = provider_symbol.strip().upper()
    if not normalized_provider or not canonical_symbol:
        return
    normalized_canonical = canonical_symbol.strip().upper()
    if not normalized_canonical:
        return
    existing_provider = canonical_to_provider.get(normalized_canonical)
    if existing_provider is None:
        canonical_to_provider[normalized_canonical] = normalized_provider
        provider_to_canonical[normalized_provider] = normalized_canonical
        if priorities is not None:
            priorities[normalized_canonical] = priority
        return
    effective_priorities = priorities or {}
    if priority < effective_priorities.get(normalized_canonical, 100):
        canonical_to_provider[normalized_canonical] = normalized_provider
        provider_to_canonical[normalized_provider] = normalized_canonical
        if priorities is not None:
            priorities[normalized_canonical] = priority
        return
    provider_to_canonical.setdefault(normalized_provider, normalized_canonical)


@dataclass(slots=True)
class SourceCapabilitySnapshot:
    source_name: str
    status: str
    discovery_mode: str
    discovered_at: datetime
    provider_symbols: list[str] = field(default_factory=list)
    canonical_to_provider: dict[str, str] = field(default_factory=dict)
    provider_to_canonical: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "status": self.status,
            "discovery_mode": self.discovery_mode,
            "discovered_at": _serialize_timestamp(self.discovered_at),
            "provider_symbols": sorted({symbol.strip().upper() for symbol in self.provider_symbols if symbol.strip()}),
            "canonical_to_provider": dict(sorted(self.canonical_to_provider.items())),
            "provider_to_canonical": dict(sorted(self.provider_to_canonical.items())),
            "notes": list(self.notes),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> SourceCapabilitySnapshot | None:
        source_name = str(payload.get("source_name") or "").strip().lower()
        if not source_name:
            return None
        provider_symbols_raw = payload.get("provider_symbols")
        provider_symbols = (
            [str(item).strip().upper() for item in provider_symbols_raw if str(item).strip()]
            if isinstance(provider_symbols_raw, list)
            else []
        )
        canonical_to_provider_raw = payload.get("canonical_to_provider")
        provider_to_canonical_raw = payload.get("provider_to_canonical")
        notes_raw = payload.get("notes")
        return cls(
            source_name=source_name,
            status=str(payload.get("status") or "unknown"),
            discovery_mode=str(payload.get("discovery_mode") or "unknown"),
            discovered_at=_parse_timestamp(str(payload.get("discovered_at") or "")) or datetime.now(tz=UTC),
            provider_symbols=provider_symbols,
            canonical_to_provider={
                str(key).strip().upper(): str(value).strip().upper()
                for key, value in (canonical_to_provider_raw or {}).items()
                if str(key).strip() and str(value).strip()
            }
            if isinstance(canonical_to_provider_raw, dict)
            else {},
            provider_to_canonical={
                str(key).strip().upper(): str(value).strip().upper()
                for key, value in (provider_to_canonical_raw or {}).items()
                if str(key).strip() and str(value).strip()
            }
            if isinstance(provider_to_canonical_raw, dict)
            else {},
            notes=[str(item).strip() for item in notes_raw if str(item).strip()] if isinstance(notes_raw, list) else [],
            error=str(payload.get("error")) if payload.get("error") not in {None, ""} else None,
        )


def _build_snapshot(
    *,
    source_name: str,
    discovery_mode: str,
    provider_symbols: list[str],
    canonical_to_provider: dict[str, str],
    provider_to_canonical: dict[str, str],
    notes: list[str] | None = None,
    status: str = "ok",
    error: str | None = None,
) -> SourceCapabilitySnapshot:
    return SourceCapabilitySnapshot(
        source_name=source_name,
        status=status,
        discovery_mode=discovery_mode,
        discovered_at=datetime.now(tz=UTC),
        provider_symbols=sorted({symbol.strip().upper() for symbol in provider_symbols if symbol.strip()}),
        canonical_to_provider=dict(sorted(canonical_to_provider.items())),
        provider_to_canonical=dict(sorted(provider_to_canonical.items())),
        notes=list(notes or []),
        error=error,
    )


def _skip_snapshot(source_name: str, *, discovery_mode: str, reason: str) -> SourceCapabilitySnapshot:
    return _build_snapshot(
        source_name=source_name,
        discovery_mode=discovery_mode,
        provider_symbols=[],
        canonical_to_provider={},
        provider_to_canonical={},
        notes=[reason],
        status="skipped",
    )


def _error_snapshot(source_name: str, *, discovery_mode: str, error: str) -> SourceCapabilitySnapshot:
    return _build_snapshot(
        source_name=source_name,
        discovery_mode=discovery_mode,
        provider_symbols=[],
        canonical_to_provider={},
        provider_to_canonical={},
        notes=[],
        status="error",
        error=error[:255],
    )


async def _request_json(client: httpx.AsyncClient, url: str, *, params: HttpQueryParams | None = None) -> dict[str, Any]:
    response = await client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object from {url}.")
    return payload


async def _request_text(client: httpx.AsyncClient, url: str, *, params: HttpQueryParams | None = None) -> str:
    response = await client.get(url, params=params)
    response.raise_for_status()
    return response.text


async def _discover_binance(client: httpx.AsyncClient, _settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    payload = await _request_json(client, "https://api.binance.com/api/v3/exchangeInfo")
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}
    priorities: dict[str, int] = {}
    for item in payload.get("symbols", []) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").upper() != "TRADING":
            continue
        if item.get("isSpotTradingAllowed") is False:
            continue
        provider_symbol = str(item.get("symbol") or "").strip().upper()
        base_symbol = str(item.get("baseAsset") or "").strip().upper()
        quote_symbol = str(item.get("quoteAsset") or "").strip().upper()
        if not provider_symbol or not base_symbol or not quote_symbol:
            continue
        if not _is_supported_crypto_base_symbol(base_symbol):
            continue
        provider_symbols.append(provider_symbol)
        canonical_symbol = _canonicalize_crypto_pair(base_symbol, quote_symbol)
        _upsert_mapping(
            canonical_to_provider,
            provider_to_canonical,
            canonical_symbol,
            provider_symbol,
            priority=EXCHANGE_STABLE_PRIORITY.get(quote_symbol, QUOTE_PRIORITY.get(quote_symbol, 50)),
            priorities=priorities,
        )
    return _build_snapshot(
        source_name="binance",
        discovery_mode="live_listing",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Filtered to spot trading symbols from exchangeInfo."],
    )


async def _discover_kucoin(client: httpx.AsyncClient, _settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    payload = await _request_json(client, "https://api.kucoin.com/api/v2/symbols")
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}
    priorities: dict[str, int] = {}
    for item in payload.get("data", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("enableTrading") is False:
            continue
        provider_symbol = str(item.get("symbol") or "").strip().upper()
        base_symbol = str(item.get("baseCurrency") or "").strip().upper()
        quote_symbol = str(item.get("quoteCurrency") or "").strip().upper()
        if not provider_symbol or not base_symbol or not quote_symbol:
            continue
        if not _is_supported_crypto_base_symbol(base_symbol):
            continue
        provider_symbols.append(provider_symbol)
        canonical_symbol = _canonicalize_crypto_pair(base_symbol, quote_symbol)
        _upsert_mapping(
            canonical_to_provider,
            provider_to_canonical,
            canonical_symbol,
            provider_symbol,
            priority=EXCHANGE_STABLE_PRIORITY.get(quote_symbol, QUOTE_PRIORITY.get(quote_symbol, 50)),
            priorities=priorities,
        )
    return _build_snapshot(
        source_name="kucoin",
        discovery_mode="live_listing",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Filtered to enabled trading symbols from KuCoin market listings."],
    )


async def _discover_coinbase(client: httpx.AsyncClient, _settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    response = await client.get("https://api.exchange.coinbase.com/products")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise TypeError("Expected Coinbase products list.")
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}
    priorities: dict[str, int] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("trading_disabled") is True:
            continue
        if str(item.get("status") or "").lower() not in {"online", ""}:
            continue
        provider_symbol = str(item.get("id") or "").strip().upper()
        base_symbol = str(item.get("base_currency") or "").strip().upper()
        quote_symbol = str(item.get("quote_currency") or "").strip().upper()
        if not provider_symbol or not base_symbol or not quote_symbol:
            continue
        if not _is_supported_crypto_base_symbol(base_symbol):
            continue
        provider_symbols.append(provider_symbol)
        canonical_symbol = _canonicalize_crypto_pair(base_symbol, quote_symbol)
        _upsert_mapping(
            canonical_to_provider,
            provider_to_canonical,
            canonical_symbol,
            provider_symbol,
            priority=QUOTE_PRIORITY.get(quote_symbol, 50),
            priorities=priorities,
        )
    return _build_snapshot(
        source_name="coinbase",
        discovery_mode="live_listing",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Filtered to online Coinbase Exchange products."],
    )


async def _discover_kraken(client: httpx.AsyncClient, _settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    payload = await _request_json(client, "https://api.kraken.com/0/public/AssetPairs")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise TypeError("Expected Kraken asset-pair result map.")
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}
    priorities: dict[str, int] = {}
    for provider_symbol, item in result.items():
        if not isinstance(item, dict):
            continue
        provider_value = str(provider_symbol).strip().upper()
        if not provider_value:
            continue
        provider_symbols.append(provider_value)
        wsname = str(item.get("wsname") or "").strip().upper()
        if "/" not in wsname:
            continue
        base_symbol, quote_symbol = wsname.split("/", 1)
        if not _is_supported_crypto_base_symbol(base_symbol):
            continue
        canonical_symbol = _canonicalize_crypto_pair(base_symbol, quote_symbol)
        raw_quote = quote_symbol.strip().upper()
        _upsert_mapping(
            canonical_to_provider,
            provider_to_canonical,
            canonical_symbol,
            provider_value,
            priority=QUOTE_PRIORITY.get(QUOTE_ALIASES.get(raw_quote, raw_quote), 50),
            priorities=priorities,
        )
    return _build_snapshot(
        source_name="kraken",
        discovery_mode="live_listing",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Canonicalized Kraken pairs from wsname values."],
    )


async def _discover_moex(client: httpx.AsyncClient, _settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    payload = await _request_json(
        client,
        "https://iss.moex.com/iss/engines/stock/markets/index/securities.json",
        params={"iss.meta": "off", "securities.columns": "SECID,SHORTNAME"},
    )
    securities = payload.get("securities") or {}
    rows = securities.get("data") if isinstance(securities, dict) else None
    if not isinstance(rows, list):
        raise TypeError("Expected MOEX securities data rows.")
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        provider_symbol = str(row[0] or "").strip().upper()
        if not provider_symbol:
            continue
        provider_symbols.append(provider_symbol)
        _upsert_mapping(canonical_to_provider, provider_to_canonical, provider_symbol, provider_symbol)
    return _build_snapshot(
        source_name="moex",
        discovery_mode="live_listing",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Loaded MOEX index securities universe from ISS."],
    )


async def _fetch_polygon_market_tickers(client: httpx.AsyncClient, api_key: str, market: str) -> list[dict[str, Any]]:
    url = "https://api.polygon.io/v3/reference/tickers"
    params: dict[str, HttpQueryValue] | None = {"market": market, "active": "true", "limit": 1000, "apiKey": api_key}
    items: list[dict[str, Any]] = []
    while url:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Expected Polygon reference response.")
        results = payload.get("results") or []
        if isinstance(results, list):
            items.extend(item for item in results if isinstance(item, dict))
        next_url = payload.get("next_url")
        if not next_url:
            break
        url = str(next_url)
        params = {"apiKey": api_key}
    return items


async def _discover_polygon(client: httpx.AsyncClient, settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    api_key = settings.polygon_api_key.strip()
    if not api_key:
        return _skip_snapshot("polygon", discovery_mode="live_listing", reason="POLYGON_API_KEY is not configured.")
    fx_items, index_items = await asyncio.gather(
        _fetch_polygon_market_tickers(client, api_key, "fx"),
        _fetch_polygon_market_tickers(client, api_key, "indices"),
    )
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}
    for item in fx_items:
        provider_symbol = str(item.get("ticker") or "").strip().upper()
        if not provider_symbol:
            continue
        provider_symbols.append(provider_symbol)
        normalized = provider_symbol.replace("C:", "")
        if len(normalized) == 6:
            canonical_symbol = _canonicalize_forex_pair(normalized[:3], normalized[3:])
            _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, provider_symbol)
    for item in index_items:
        provider_symbol = str(item.get("ticker") or "").strip().upper()
        if not provider_symbol:
            continue
        provider_symbols.append(provider_symbol)
        canonical_symbol = POLYGON_REVERSE_ALIASES.get(provider_symbol, _canonicalize_generic_symbol(provider_symbol))
        _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, provider_symbol)
    return _build_snapshot(
        source_name="polygon",
        discovery_mode="live_listing",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Merged active Polygon FX and index reference universes."],
    )


async def _discover_twelvedata(client: httpx.AsyncClient, settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    api_key = settings.twelve_data_api_key.strip()
    if not api_key:
        return _skip_snapshot("twelvedata", discovery_mode="live_listing", reason="TWELVE_DATA_API_KEY is not configured.")
    forex_payload, indices_payload, commodities_payload = await asyncio.gather(
        _request_json(client, "https://api.twelvedata.com/forex_pairs", params={"apikey": api_key}),
        _request_json(client, "https://api.twelvedata.com/indices", params={"apikey": api_key}),
        _request_json(client, "https://api.twelvedata.com/commodities", params={"apikey": api_key}),
    )
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}
    for item in forex_payload.get("data", []) or []:
        if not isinstance(item, dict):
            continue
        provider_symbol = str(item.get("symbol") or "").strip().upper()
        if not provider_symbol or "/" not in provider_symbol:
            continue
        provider_symbols.append(provider_symbol)
        base_symbol, quote_symbol = provider_symbol.split("/", 1)
        canonical_symbol = _canonicalize_forex_pair(base_symbol, quote_symbol)
        _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, provider_symbol)
    for payload in (indices_payload, commodities_payload):
        for item in payload.get("data", []) or []:
            if not isinstance(item, dict):
                continue
            provider_symbol = str(item.get("symbol") or "").strip().upper()
            if not provider_symbol:
                continue
            provider_symbols.append(provider_symbol)
            canonical_symbol = TWELVE_DATA_REVERSE_ALIASES.get(provider_symbol, _canonicalize_generic_symbol(provider_symbol))
            _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, provider_symbol)
    return _build_snapshot(
        source_name="twelvedata",
        discovery_mode="live_listing",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Merged TwelveData forex, index, and commodity listings."],
    )


async def _discover_alphavantage(client: httpx.AsyncClient, settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    api_key = settings.alpha_vantage_api_key.strip()
    if not api_key:
        return _skip_snapshot("alphavantage", discovery_mode="derived_currency_universe", reason="ALPHA_VANTAGE_API_KEY is not configured.")
    payload = await _request_text(client, "https://www.alphavantage.co/physical_currency_list/")
    reader = csv.DictReader(StringIO(payload))
    currencies = sorted(
        {
            str(row.get("currency code") or "").strip().upper()
            for row in reader
            if isinstance(row, dict) and str(row.get("currency code") or "").strip()
        }
    )
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}
    for base_symbol, quote_symbol in product(currencies, currencies):
        if base_symbol == quote_symbol:
            continue
        canonical_symbol = ALPHA_VANTAGE_REVERSE_ALIASES.get(
            f"{base_symbol}{quote_symbol}",
            _canonicalize_forex_pair(base_symbol, quote_symbol),
        )
        provider_symbol = f"{base_symbol}{quote_symbol}"
        provider_symbols.append(provider_symbol)
        _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, provider_symbol)

    async def _validate_special(canonical_symbol: str, spec: AlphaVantageSeriesSpec) -> tuple[str, str | None]:
        params = {"function": str(spec["function"]), "apikey": api_key}
        if spec.get("interval") is not None:
            params["interval"] = str(spec["interval"])
        if spec.get("maturity") is not None:
            params["maturity"] = str(spec["maturity"])
        payload = await _request_json(client, "https://www.alphavantage.co/query", params=params)
        if isinstance(payload.get("data"), list):
            return canonical_symbol, str(spec["provider_symbol"]).strip().upper()
        return canonical_symbol, None

    special_results: list[tuple[str, str | None]] = await asyncio.gather(
        *(_validate_special(canonical_symbol, spec) for canonical_symbol, spec in ALPHA_VANTAGE_SPECIAL_SERIES.items())
    )
    for canonical_symbol, special_provider_symbol in special_results:
        if special_provider_symbol is None:
            continue
        provider_symbols.append(special_provider_symbol)
        _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, special_provider_symbol)
    return _build_snapshot(
        source_name="alphavantage",
        discovery_mode="derived_currency_universe",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Generated ordered FX pair universe from AlphaVantage physical currency list and validated curated energy/rates aliases."],
    )


async def _discover_eia(client: httpx.AsyncClient, settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    api_key = settings.eia_api_key.strip()
    if not api_key:
        return _skip_snapshot("eia", discovery_mode="validated_aliases", reason="EIA_API_KEY is not configured.")

    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}

    async def _validate(provider_symbol: str) -> tuple[str, bool]:
        payload = await _request_json(
            client,
            f"https://api.eia.gov/v2/seriesid/{provider_symbol}",
            params={"api_key": api_key, "out": "json"},
        )
        response_payload = payload.get("response")
        return provider_symbol, isinstance(response_payload, dict) and isinstance(response_payload.get("data"), list)

    results = await asyncio.gather(*(_validate(symbol) for symbol in sorted(EIA_REVERSE_ALIASES.keys())))
    for provider_symbol, is_valid in results:
        if not is_valid:
            continue
        normalized_provider = provider_symbol.strip().upper()
        provider_symbols.append(normalized_provider)
        canonical_symbol = EIA_REVERSE_ALIASES.get(provider_symbol)
        _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, normalized_provider)
    return _build_snapshot(
        source_name="eia",
        discovery_mode="validated_aliases",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Validated curated EIA daily energy aliases through seriesid endpoint."],
    )


async def _discover_fred(client: httpx.AsyncClient, settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    api_key = settings.fred_api_key.strip()
    if not api_key:
        return _skip_snapshot("fred", discovery_mode="validated_aliases", reason="FRED_API_KEY is not configured.")

    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}

    async def _validate(provider_symbol: str) -> tuple[str, bool]:
        payload = await _request_json(
            client,
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": provider_symbol,
                "api_key": api_key,
                "file_type": "json",
                "limit": 1,
                "sort_order": "desc",
            },
        )
        return provider_symbol, isinstance(payload.get("observations"), list)

    results = await asyncio.gather(*(_validate(symbol) for symbol in sorted(FRED_REVERSE_ALIASES.keys())))
    for provider_symbol, is_valid in results:
        if not is_valid:
            continue
        normalized_provider = provider_symbol.strip().upper()
        provider_symbols.append(normalized_provider)
        canonical_symbol = FRED_REVERSE_ALIASES.get(provider_symbol)
        _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, normalized_provider)
    return _build_snapshot(
        source_name="fred",
        discovery_mode="validated_aliases",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Validated curated FRED macro aliases through series observations endpoint."],
    )


async def _discover_yahoo(client: httpx.AsyncClient, _settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    response = await client.get(
        "https://query1.finance.yahoo.com/v7/finance/quote",
        params={"symbols": ",".join(sorted(YAHOO_SYMBOLS.values()))},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        },
    )
    response.raise_for_status()
    payload = response.json()
    quote_response = payload.get("quoteResponse") or {}
    results = quote_response.get("result") if isinstance(quote_response, dict) else None
    if not isinstance(results, list):
        raise TypeError("Expected Yahoo quoteResponse.result list.")
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        provider_symbol = str(item.get("symbol") or "").strip().upper()
        if not provider_symbol:
            continue
        provider_symbols.append(provider_symbol)
        canonical_symbol = YAHOO_REVERSE_ALIASES.get(provider_symbol)
        _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, provider_symbol)
    return _build_snapshot(
        source_name="yahoo",
        discovery_mode="validated_aliases",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Validated curated Yahoo aliases through quote endpoint; upstream does not expose a bulk universe listing used by IRIS."],
    )


async def _discover_stooq(client: httpx.AsyncClient, _settings: _CapabilitySettings) -> SourceCapabilitySnapshot:
    provider_symbols: list[str] = []
    canonical_to_provider: dict[str, str] = {}
    provider_to_canonical: dict[str, str] = {}

    async def _validate(provider_symbol: str) -> tuple[str, bool]:
        text = await _request_text(
            client,
            "https://stooq.com/q/d/l/",
            params={"s": provider_symbol, "i": "d"},
        )
        normalized = text.strip().lower()
        return provider_symbol, bool(normalized and normalized != "no data")

    results = await asyncio.gather(*(_validate(symbol) for symbol in sorted(STOOQ_REVERSE_ALIASES.keys())))
    for provider_symbol, is_valid in results:
        if not is_valid:
            continue
        normalized_provider = provider_symbol.strip().upper()
        provider_symbols.append(normalized_provider)
        canonical_symbol = STOOQ_REVERSE_ALIASES.get(provider_symbol)
        _upsert_mapping(canonical_to_provider, provider_to_canonical, canonical_symbol, normalized_provider)
    return _build_snapshot(
        source_name="stooq",
        discovery_mode="validated_aliases",
        provider_symbols=provider_symbols,
        canonical_to_provider=canonical_to_provider,
        provider_to_canonical=provider_to_canonical,
        notes=["Validated curated Stooq aliases through daily CSV endpoint; no bulk listing endpoint is used by IRIS."],
    )


DISCOVERERS: tuple[_Discoverer, ...] = (
    _discover_binance,
    _discover_kucoin,
    _discover_coinbase,
    _discover_kraken,
    _discover_moex,
    _discover_eia,
    _discover_fred,
    _discover_polygon,
    _discover_twelvedata,
    _discover_alphavantage,
    _discover_yahoo,
    _discover_stooq,
)


class MarketSourceCapabilityRegistry:
    def __init__(self) -> None:
        self.settings: _CapabilitySettings = get_settings()
        self._lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._started = False
        self._client: httpx.AsyncClient | None = None
        self._snapshots: dict[str, SourceCapabilitySnapshot] = {}

    async def start(self) -> None:
        async with self._start_lock:
            if self._started:
                return
            await self._load_from_redis()
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0),
                headers={
                    "User-Agent": "IRIS/0.1 source-capability-registry",
                    "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
                },
                follow_redirects=True,
                trust_env=False,
            )
            self._started = True

    async def stop(self) -> None:
        async with self._start_lock:
            if not self._started:
                return
            if self._client is not None:
                await self._client.aclose()
            self._client = None
            self._started = False

    async def refresh_once(self) -> dict[str, object]:
        if not self._started:
            await self.start()
        if self._client is None:
            raise RuntimeError("Source capability registry HTTP client was not initialized.")
        async with self._lock:
            previous_snapshots = dict(self._snapshots)
        snapshots = await asyncio.gather(
            *(self._discover_with_guard(discoverer) for discoverer in DISCOVERERS),
            return_exceptions=False,
        )
        snapshot_map = {
            snapshot.source_name: self._merge_with_previous_snapshot(previous_snapshots.get(snapshot.source_name), snapshot)
            for snapshot in snapshots
        }
        async with self._lock:
            self._snapshots = snapshot_map
            await self._persist_to_redis()
        return {
            "status": "ok",
            "sources": {
                source_name: {
                    "status": snapshot.status,
                    "mode": snapshot.discovery_mode,
                    "provider_symbols": len(snapshot.provider_symbols),
                    "mapped_symbols": len(snapshot.canonical_to_provider),
                    "error": snapshot.error,
                }
                for source_name, snapshot in sorted(snapshot_map.items())
            },
        }

    def _merge_with_previous_snapshot(
        self,
        previous: SourceCapabilitySnapshot | None,
        current: SourceCapabilitySnapshot,
    ) -> SourceCapabilitySnapshot:
        if current.status != "error" or previous is None:
            return current
        return SourceCapabilitySnapshot(
            source_name=previous.source_name,
            status="stale",
            discovery_mode=previous.discovery_mode,
            discovered_at=previous.discovered_at,
            provider_symbols=list(previous.provider_symbols),
            canonical_to_provider=dict(previous.canonical_to_provider),
            provider_to_canonical=dict(previous.provider_to_canonical),
            notes=[*previous.notes, "Refresh failed; preserved previous snapshot."],
            error=current.error,
        )

    def resolve_provider_symbol(
        self,
        source_name: str,
        canonical_symbol: str,
        *,
        fallback: str | None = None,
    ) -> str | None:
        snapshot = self._snapshots.get(source_name.strip().lower())
        if snapshot is None:
            return fallback
        return snapshot.canonical_to_provider.get(canonical_symbol.strip().upper(), fallback)

    def supports_canonical_symbol(
        self,
        source_name: str,
        canonical_symbol: str,
        *,
        fallback: bool = False,
    ) -> bool:
        snapshot = self._snapshots.get(source_name.strip().lower())
        if snapshot is None:
            return fallback
        return canonical_symbol.strip().upper() in snapshot.canonical_to_provider

    async def _discover_with_guard(self, discoverer: _Discoverer) -> SourceCapabilitySnapshot:
        source_name = discoverer.__name__.removeprefix("_discover_")
        try:
            if self._client is None:
                raise RuntimeError("Source capability registry HTTP client was not initialized.")
            return await discoverer(self._client, self.settings)
        except Exception as exc:  # pragma: no cover - runtime shield
            error_message, context = _classify_discovery_error(exc)
            if isinstance(exc, httpx.HTTPError):
                LOGGER.warning(
                    "Market source capability discovery degraded for %s: %s.",
                    source_name,
                    error_message,
                    extra={
                        "source_capability_registry": {
                            "event": "market_source_capability.discovery.degraded",
                            "source_name": source_name,
                            **context,
                        }
                    },
                )
            else:
                LOGGER.exception("Market source capability discovery failed for %s.", source_name)
            return _error_snapshot(source_name, discovery_mode="live_listing", error=error_message)

    async def _load_from_redis(self) -> None:
        raw = await (await get_async_lock_redis()).get(REDIS_KEY)
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            LOGGER.warning("Ignoring invalid market source capability registry payload in Redis.")
            return
        if not isinstance(payload, dict):
            return
        snapshots_raw = payload.get("sources")
        if not isinstance(snapshots_raw, dict):
            return
        snapshots: dict[str, SourceCapabilitySnapshot] = {}
        for source_name, source_payload in snapshots_raw.items():
            if not isinstance(source_payload, dict):
                continue
            snapshot = SourceCapabilitySnapshot.from_dict(
                {"source_name": source_name, **source_payload},
            )
            if snapshot is not None:
                snapshots[snapshot.source_name] = snapshot
        self._snapshots = snapshots

    async def _persist_to_redis(self) -> None:
        payload = {
            "updated_at": _serialize_timestamp(datetime.now(tz=UTC)),
            "sources": {
                source_name: {
                    key: value
                    for key, value in snapshot.to_dict().items()
                    if key != "source_name"
                }
                for source_name, snapshot in sorted(self._snapshots.items())
            },
        }
        await (await get_async_lock_redis()).set(REDIS_KEY, json.dumps(payload, separators=(",", ":"), sort_keys=True))


_registry: MarketSourceCapabilityRegistry | None = None
_registry_lock = Lock()


def get_market_source_capability_registry() -> MarketSourceCapabilityRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = MarketSourceCapabilityRegistry()
    return _registry


__all__ = [
    "MarketSourceCapabilityRegistry",
    "SourceCapabilitySnapshot",
    "get_market_source_capability_registry",
]
