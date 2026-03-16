from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.market_data import candles as market_data_candles
from src.apps.market_data import domain as market_data_domain
from src.apps.market_data import support as market_data_support
from src.apps.market_data.contracts import (
    coin_create_input_from_payload,
    price_history_create_input_from_payload,
    serialize_candle_contracts,
)
from src.apps.market_data.models import Coin
from src.apps.market_data.query_services import MarketDataQueryService
from src.apps.market_data.read_models import (
    CoinReadModel,
    PriceHistoryReadModel,
    coin_read_model_from_orm,
    price_history_read_model,
)
from src.apps.market_data.repositories import (
    CandleRepository,
    CoinMetricsRepository,
    CoinRepository,
    IndicatorCacheRepository,
    SignalRepository,
)
from src.core.db.uow import BaseAsyncUnitOfWork


def _normalized_coin_values(payload: object) -> dict[str, object]:
    coin_input = coin_create_input_from_payload(payload)
    return {
        "symbol": coin_input.symbol,
        "name": coin_input.name,
        "asset_type": coin_input.asset_type,
        "theme": coin_input.theme,
        "sector_code": (coin_input.sector or coin_input.theme).strip().lower(),
        "source": coin_input.source,
        "enabled": coin_input.enabled,
        "sort_order": coin_input.sort_order,
        "candles_config": serialize_candle_contracts(coin_input.candles),
    }


def _reset_history_sync_state(coin: Coin) -> None:
    coin.history_backfill_completed_at = None
    coin.last_history_sync_at = None
    coin.next_history_sync_at = None
    coin.last_history_sync_error = None


async def _coin_read_after_write(
    db: AsyncSession,
    coin: Coin,
    *,
    include_deleted: bool = False,
) -> CoinReadModel:
    item = await MarketDataQueryService(db).get_coin_read_by_symbol(coin.symbol, include_deleted=include_deleted)
    return item if item is not None else coin_read_model_from_orm(coin)


async def _create_or_update_coin_async(
    uow: BaseAsyncUnitOfWork,
    payload: object,
) -> Coin:
    db = uow.session
    coins = CoinRepository(db)
    metrics = CoinMetricsRepository(db)
    normalized = _normalized_coin_values(payload)
    existing = await coins.get_by_symbol(str(normalized["symbol"]), include_deleted=True)

    if existing is not None:
        was_deleted = existing.deleted_at is not None
        sync_settings_changed = (
            existing.asset_type != normalized["asset_type"]
            or existing.source != normalized["source"]
            or existing.candles_config != normalized["candles_config"]
        )
        existing.name = normalized["name"]
        existing.asset_type = normalized["asset_type"]
        existing.theme = normalized["theme"]
        existing.sector_code = normalized["sector_code"]
        existing.source = normalized["source"]
        existing.enabled = normalized["enabled"]
        existing.sort_order = normalized["sort_order"]
        existing.candles_config = normalized["candles_config"]
        existing.deleted_at = None
        if was_deleted or sync_settings_changed:
            _reset_history_sync_state(existing)
        await metrics.ensure_row(int(existing.id))
        return existing

    coin = Coin(
        symbol=normalized["symbol"],
        name=normalized["name"],
        asset_type=normalized["asset_type"],
        theme=normalized["theme"],
        sector_code=normalized["sector_code"],
        source=normalized["source"],
        enabled=normalized["enabled"],
        sort_order=normalized["sort_order"],
        candles_config=normalized["candles_config"],
    )
    await coins.add(coin)
    await metrics.ensure_row(int(coin.id))
    return coin


async def _delete_coin_async(
    uow: BaseAsyncUnitOfWork,
    coin: Coin,
) -> None:
    db = uow.session
    candles = CandleRepository(db)
    indicator_cache = IndicatorCacheRepository(db)
    signals = SignalRepository(db)
    metrics = CoinMetricsRepository(db)

    await candles.delete_by_coin_id(int(coin.id))
    await indicator_cache.delete_by_coin_id(int(coin.id))
    await signals.delete_by_coin_id(int(coin.id))
    await metrics.delete_by_coin_id(int(coin.id))
    coin.enabled = False
    coin.deleted_at = market_data_domain.utc_now()
    _reset_history_sync_state(coin)


async def _create_price_history_async_internal(
    uow: BaseAsyncUnitOfWork,
    coin: Coin,
    payload: object,
) -> PriceHistoryReadModel:
    db = uow.session
    history_input = price_history_create_input_from_payload(payload)
    resolved_interval = market_data_support.resolve_history_interval(coin, history_input.interval)
    base_interval = str(market_data_support.get_base_candle_config(coin)["interval"])
    if resolved_interval != base_interval:
        raise ValueError(f"Manual history writes are only supported for the {base_interval} base timeframe.")

    timeframe = market_data_candles.interval_to_timeframe(resolved_interval)
    timestamp = market_data_candles.align_timeframe_timestamp(history_input.timestamp, timeframe)
    close = float(history_input.price)
    volume = float(history_input.volume) if history_input.volume is not None else None
    await CandleRepository(db).upsert_row(
        coin_id=int(coin.id),
        timeframe=timeframe,
        timestamp=timestamp,
        open_price=close,
        high_price=close,
        low_price=close,
        close_price=close,
        volume=volume,
    )
    uow.add_after_commit_action(
        lambda coin_id=int(coin.id), timeframe=timeframe, timestamp=timestamp: market_data_support.publish_candle_events(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            created_count=1,
            source="manual",
        )
    )
    return price_history_read_model(
        coin_id=int(coin.id),
        interval=resolved_interval,
        timestamp=timestamp,
        price=close,
        volume=volume,
    )


__all__ = [
    "_coin_read_after_write",
    "_create_or_update_coin_async",
    "_create_price_history_async_internal",
    "_delete_coin_async",
]
