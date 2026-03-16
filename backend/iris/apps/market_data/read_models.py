from dataclasses import dataclass
from datetime import datetime

from iris.apps.market_data.models import Coin
from iris.apps.market_data.schemas import CandleConfig


@dataclass(slots=True, frozen=True)
class CandleConfigReadModel:
    interval: str
    retention_bars: int


@dataclass(slots=True, frozen=True)
class CoinReadModel:
    id: int
    symbol: str
    name: str
    asset_type: str
    theme: str
    sector: str
    source: str
    enabled: bool
    auto_watch_enabled: bool
    auto_watch_source: str | None
    sort_order: int
    candles: tuple[CandleConfigReadModel, ...]
    created_at: datetime
    history_backfill_completed_at: datetime | None
    last_history_sync_at: datetime | None
    next_history_sync_at: datetime | None
    last_history_sync_error: str | None


@dataclass(slots=True, frozen=True)
class PriceHistoryReadModel:
    coin_id: int
    interval: str
    timestamp: datetime
    price: float
    volume: float | None


def candle_config_read_model_from_payload(payload: object) -> CandleConfigReadModel:
    config = CandleConfig.model_validate(payload)
    return CandleConfigReadModel(
        interval=str(config.interval),
        retention_bars=int(config.retention_bars),
    )


def coin_read_model_from_orm(coin: Coin) -> CoinReadModel:
    candles = tuple(candle_config_read_model_from_payload(item) for item in coin.candles_config or ())
    return CoinReadModel(
        id=int(coin.id),
        symbol=str(coin.symbol),
        name=str(coin.name),
        asset_type=str(coin.asset_type),
        theme=str(coin.theme),
        sector=str(coin.sector_code),
        source=str(coin.source),
        enabled=bool(coin.enabled),
        auto_watch_enabled=bool(coin.auto_watch_enabled),
        auto_watch_source=str(coin.auto_watch_source) if coin.auto_watch_source is not None else None,
        sort_order=int(coin.sort_order),
        candles=candles,
        created_at=coin.created_at,
        history_backfill_completed_at=coin.history_backfill_completed_at,
        last_history_sync_at=coin.last_history_sync_at,
        next_history_sync_at=coin.next_history_sync_at,
        last_history_sync_error=str(coin.last_history_sync_error) if coin.last_history_sync_error is not None else None,
    )


def price_history_read_model(
    *,
    coin_id: int,
    interval: str,
    timestamp: datetime,
    price: float,
    volume: float | None,
) -> PriceHistoryReadModel:
    return PriceHistoryReadModel(
        coin_id=int(coin_id),
        interval=str(interval),
        timestamp=timestamp,
        price=float(price),
        volume=float(volume) if volume is not None else None,
    )


__all__ = [
    "CandleConfigReadModel",
    "CoinReadModel",
    "PriceHistoryReadModel",
    "candle_config_read_model_from_payload",
    "coin_read_model_from_orm",
    "price_history_read_model",
]
