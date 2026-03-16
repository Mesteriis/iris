from datetime import timedelta
from types import SimpleNamespace

from src.apps.market_data import domain as market_data_domain
from src.apps.market_data import support as market_data_support
from src.apps.market_data.command_support import (
    _coin_read_after_write,
    _create_or_update_coin_async,
    _create_price_history_async_internal,
    _delete_coin_async,
)
from src.apps.market_data.history_sync import (
    _calculate_backfill_progress_async,
    _coin_has_base_candles_async,
    _get_latest_candle_timestamp_async,
    _get_latest_history_timestamp_async,
    _prune_future_price_history_async,
    _prune_price_history_async,
    _refresh_continuous_aggregate_range_async,
    _upsert_base_candles_async,
)
from src.apps.market_data.models import Coin
from src.apps.market_data.read_models import CoinReadModel, PriceHistoryReadModel
from src.apps.market_data.repositories import CoinRepository
from src.apps.market_data.results import MarketDataHistorySyncResult
from src.apps.market_data.sources import get_market_source_carousel
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.messages import (
    publish_coin_analysis_messages,
    publish_coin_history_loaded_message,
    publish_coin_history_progress_message,
)


def _coin_message_proxy(coin: Coin) -> SimpleNamespace:
    return SimpleNamespace(
        id=int(coin.id),
        symbol=str(coin.symbol),
        name=str(getattr(coin, "name", coin.symbol)),
        asset_type=str(getattr(coin, "asset_type", "unknown")),
    )


class MarketDataService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._coins = CoinRepository(uow.session)

    async def create_coin(self, payload: object) -> CoinReadModel:
        coin = await _create_or_update_coin_async(self._uow, payload)
        return await _coin_read_after_write(self._uow.session, coin, include_deleted=True)

    async def delete_coin(self, symbol: str) -> bool:
        coin = await self._coins.get_for_update_by_symbol(symbol)
        if coin is None:
            return False
        await _delete_coin_async(self._uow, coin)
        return True

    async def create_price_history(
        self,
        *,
        symbol: str,
        payload,
    ) -> PriceHistoryReadModel | None:
        coin = await self._coins.get_for_update_by_symbol(symbol)
        if coin is None:
            return None
        return await _create_price_history_async_internal(self._uow, coin, payload)


class MarketDataHistorySyncService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._coins = CoinRepository(uow.session)

    async def sync_coin_history_backfill(
        self,
        *,
        symbol: str,
        force: bool = False,
    ) -> MarketDataHistorySyncResult:
        coin = await self._coins.get_for_update_by_symbol(symbol)
        if coin is None:
            return MarketDataHistorySyncResult(
                status="error",
                symbol=symbol.strip().upper(),
                reason="coin_not_found",
            )
        return await _sync_coin_history_async(self._uow, coin, history_mode="backfill", force=force)

    async def sync_coin_latest_history(
        self,
        *,
        symbol: str,
        force: bool = False,
    ) -> MarketDataHistorySyncResult:
        coin = await self._coins.get_for_update_by_symbol(symbol)
        if coin is None:
            return MarketDataHistorySyncResult(
                status="error",
                symbol=symbol.strip().upper(),
                reason="coin_not_found",
            )
        if coin.history_backfill_completed_at is None:
            return MarketDataHistorySyncResult(
                status="pending_backfill",
                symbol=coin.symbol,
            )
        return await _sync_coin_history_async(self._uow, coin, history_mode="latest", force=force)


async def _sync_coin_history_async(
    uow: BaseAsyncUnitOfWork,
    coin: Coin,
    *,
    history_mode: str,
    force: bool = False,
) -> MarketDataHistorySyncResult:
    db = uow.session
    if coin.deleted_at is not None or not coin.enabled:
        return MarketDataHistorySyncResult(
            status="skipped",
            symbol=coin.symbol,
        )

    now = market_data_domain.utc_now()
    if not force and coin.next_history_sync_at is not None and coin.next_history_sync_at > now:
        return MarketDataHistorySyncResult(
            status="deferred",
            symbol=coin.symbol,
            retry_at=coin.next_history_sync_at.isoformat(),
        )

    total_created = 0
    candles = market_data_support.serialize_candles(coin.candles_config or [])
    base_candle = market_data_support.get_base_candle_config(coin)
    interval = market_data_domain.normalize_interval(str(base_candle["interval"]))
    retention_bars = int(base_candle["retention_bars"])
    carousel = get_market_source_carousel()
    last_progress_percent: float | None = None

    if history_mode == "backfill":
        loaded_points, total_points, progress_percent = await _calculate_backfill_progress_async(
            db,
            coin_id=int(coin.id),
            candles=candles,
            reference_time=now,
        )
        publish_coin_history_progress_message(
            coin,
            progress_percent=progress_percent,
            loaded_points=loaded_points,
            total_points=total_points,
        )
        last_progress_percent = progress_percent

    latest_available = market_data_domain.latest_completed_timestamp(interval, now)
    await _prune_future_price_history_async(
        uow,
        coin_id=int(coin.id),
        interval=interval,
        latest_allowed=latest_available,
    )
    latest_existing = await _get_latest_history_timestamp_async(db, coin_id=int(coin.id), interval=interval)

    if history_mode == "backfill":
        start = market_data_domain.history_window_start(latest_available, interval, retention_bars)
    elif latest_existing is None:
        start = latest_available
    else:
        start = latest_existing + market_data_domain.interval_delta(interval)

    if start <= latest_available:
        fetch_result = await carousel.fetch_history_window(coin, interval, start, latest_available)
        await _upsert_base_candles_async(
            uow,
            coin_id=int(coin.id),
            interval=interval,
            bars=fetch_result.bars,
            source=history_mode,
        )
        total_created += len(fetch_result.bars)
        await _prune_price_history_async(
            uow,
            coin_id=int(coin.id),
            interval=interval,
            retention_bars=retention_bars,
        )

        if history_mode == "backfill":
            loaded_points, total_points, progress_percent = await _calculate_backfill_progress_async(
                db,
                coin_id=int(coin.id),
                candles=candles,
                reference_time=now,
            )
            if progress_percent != last_progress_percent:
                publish_coin_history_progress_message(
                    coin,
                    progress_percent=progress_percent,
                    loaded_points=loaded_points,
                    total_points=total_points,
                )
                last_progress_percent = progress_percent

        if not fetch_result.completed:
            retry_after_seconds = max(int(fetch_result.retry_after_seconds or 3600), 1)
            coin.last_history_sync_at = now
            coin.next_history_sync_at = now + timedelta(seconds=retry_after_seconds)
            coin.last_history_sync_error = (fetch_result.error or "Market source carousel exhausted.")[:255]
            return MarketDataHistorySyncResult(
                status="backoff",
                symbol=coin.symbol,
                created=total_created,
                retry_at=coin.next_history_sync_at.isoformat(),
                reason=str(coin.last_history_sync_error),
            )
    else:
        await _prune_price_history_async(
            uow,
            coin_id=int(coin.id),
            interval=interval,
            retention_bars=retention_bars,
        )

    if history_mode == "backfill":
        coin.history_backfill_completed_at = now
    coin.last_history_sync_at = now
    coin.next_history_sync_at = None
    coin.last_history_sync_error = None

    if history_mode == "backfill":
        loaded_points, total_points, _ = await _calculate_backfill_progress_async(
            db,
            coin_id=int(coin.id),
            candles=candles,
            reference_time=now,
        )
        message_coin = _coin_message_proxy(coin)
        if last_progress_percent != 100.0:
            uow.add_after_commit_action(
                lambda coin=message_coin, loaded_points=loaded_points, total_points=total_points: publish_coin_history_progress_message(
                    coin,
                    progress_percent=100.0,
                    loaded_points=loaded_points,
                    total_points=total_points,
                )
            )
        uow.add_after_commit_action(
            lambda coin=message_coin, total_points=total_points: publish_coin_history_loaded_message(
                coin,
                total_points=total_points,
            )
        )
        uow.add_after_commit_action(lambda coin=message_coin: publish_coin_analysis_messages(coin))

    return MarketDataHistorySyncResult(
        status="ok",
        symbol=coin.symbol,
        created=total_created,
    )


__all__ = ["MarketDataHistorySyncService", "MarketDataService"]
