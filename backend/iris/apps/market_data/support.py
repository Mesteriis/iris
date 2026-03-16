from collections.abc import Sequence
from datetime import datetime
from typing import Any

from iris.apps.market_data.candles import interval_to_timeframe
from iris.apps.market_data.domain import normalize_interval
from iris.apps.market_data.models import Coin
from iris.apps.market_data.schemas import CandleConfig
from iris.runtime.streams.publisher import publish_event

_DEFAULT_BASE_INTERVAL = "15m"
_DEFAULT_RETENTION_BARS = 20160


def publish_candle_events(
    *,
    coin_id: int,
    timeframe: int,
    timestamp: datetime,
    created_count: int,
    source: str,
) -> None:
    payload = {
        "coin_id": coin_id,
        "timeframe": timeframe,
        "timestamp": timestamp,
        "created_count": created_count,
        "source": source,
    }
    publish_event("candle_inserted", payload)
    publish_event("candle_closed", payload)


def serialize_candles(candles: Sequence[CandleConfig | dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        CandleConfig.model_validate(candle).model_dump()
        if not isinstance(candle, CandleConfig)
        else candle.model_dump()
        for candle in candles
    ]


def get_base_candle_config(coin: Coin) -> dict[str, Any]:
    candles = serialize_candles(coin.candles_config or [])
    if not candles:
        return {"interval": _DEFAULT_BASE_INTERVAL, "retention_bars": _DEFAULT_RETENTION_BARS}

    normalized = [
        {
            "interval": normalize_interval(str(candle["interval"])),
            "retention_bars": int(candle["retention_bars"]),
        }
        for candle in candles
    ]
    return min(normalized, key=lambda candle: interval_to_timeframe(str(candle["interval"])))


def get_interval_retention_bars(coin: Coin, interval: str) -> int:
    normalized_interval = normalize_interval(interval)
    candles = serialize_candles(coin.candles_config or [])
    for candle in candles:
        if normalize_interval(str(candle["interval"])) == normalized_interval:
            return int(candle["retention_bars"])
    return int(get_base_candle_config(coin)["retention_bars"])


def get_coin_base_timeframe(coin: Coin) -> int:
    return interval_to_timeframe(str(get_base_candle_config(coin)["interval"]))


def resolve_history_interval(coin: Coin, interval: str | None = None) -> str:
    if interval:
        return normalize_interval(interval)
    return str(get_base_candle_config(coin)["interval"])


__all__ = [
    "get_base_candle_config",
    "get_coin_base_timeframe",
    "get_interval_retention_bars",
    "publish_candle_events",
    "resolve_history_interval",
    "serialize_candles",
]
