from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.apps.market_data.domain import ensure_utc, normalize_interval


def _read_value(payload: object, name: str, default: object | None = None) -> object | None:
    if isinstance(payload, dict):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _int_value(value: object | None, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    try:
        return default if value is None else int(str(value))
    except (TypeError, ValueError):
        return default


def _float_value(value: object | None, *, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    try:
        return default if value is None else float(str(value))
    except (TypeError, ValueError):
        return default


def _optional_float_value(value: object | None) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    try:
        return None if value is None else float(str(value))
    except (TypeError, ValueError):
        return None


def _sequence_value(value: object | None) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(value)
    return ()


@dataclass(slots=True, frozen=True)
class CandleConfigInput:
    interval: str
    retention_bars: int


@dataclass(slots=True, frozen=True)
class CoinCreateInput:
    symbol: str
    name: str
    asset_type: str
    theme: str
    sector: str | None
    source: str
    enabled: bool
    sort_order: int
    candles: tuple[CandleConfigInput, ...]


@dataclass(slots=True, frozen=True)
class PriceHistoryCreateInput:
    interval: str
    timestamp: datetime
    price: float
    volume: float | None


def candle_config_input_from_payload(payload: object) -> CandleConfigInput:
    return CandleConfigInput(
        interval=normalize_interval(str(_read_value(payload, "interval", "15m"))),
        retention_bars=max(_int_value(_read_value(payload, "retention_bars", 1), default=1), 1),
    )


def serialize_candle_contracts(candles: tuple[CandleConfigInput, ...]) -> list[dict[str, Any]]:
    return [
        {
            "interval": candle.interval,
            "retention_bars": int(candle.retention_bars),
        }
        for candle in candles
    ]


def coin_create_input_from_payload(payload: object) -> CoinCreateInput:
    raw_sector = _read_value(payload, "sector")
    candles_payload = _sequence_value(_read_value(payload, "candles", ()))
    return CoinCreateInput(
        symbol=str(_read_value(payload, "symbol", "")).strip().upper(),
        name=str(_read_value(payload, "name", "")).strip(),
        asset_type=str(_read_value(payload, "asset_type", "crypto")).strip().lower(),
        theme=str(_read_value(payload, "theme", "core")).strip().lower(),
        sector=str(raw_sector).strip().lower() if raw_sector is not None else None,
        source=str(_read_value(payload, "source", "default")).strip().lower(),
        enabled=bool(_read_value(payload, "enabled", True)),
        sort_order=_int_value(_read_value(payload, "sort_order", 0), default=0),
        candles=tuple(candle_config_input_from_payload(item) for item in candles_payload),
    )


def price_history_create_input_from_payload(payload: object) -> PriceHistoryCreateInput:
    raw_timestamp = _read_value(payload, "timestamp")
    if not isinstance(raw_timestamp, datetime):
        raise TypeError("Price history payload must provide a datetime timestamp.")
    return PriceHistoryCreateInput(
        interval=normalize_interval(str(_read_value(payload, "interval", "1h"))),
        timestamp=ensure_utc(raw_timestamp),
        price=_float_value(_read_value(payload, "price", 0.0), default=0.0),
        volume=_optional_float_value(_read_value(payload, "volume")),
    )


__all__ = [
    "CandleConfigInput",
    "CoinCreateInput",
    "PriceHistoryCreateInput",
    "candle_config_input_from_payload",
    "coin_create_input_from_payload",
    "price_history_create_input_from_payload",
    "serialize_candle_contracts",
]
