from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.market_data import domain as market_data_domain
from src.apps.market_data import repos as market_data_repos
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
    TimescaleContinuousAggregateRepository,
)
from src.apps.market_data import support as market_data_support
from src.apps.market_data.schemas import CandleConfig, CoinCreate
from src.apps.market_data.sources import get_market_source_carousel
from src.core.db.session import async_engine
from src.core.db.uow import BaseAsyncUnitOfWork
from src.core.watched_assets import WATCHED_ASSETS
from src.runtime.streams.messages import (
    publish_coin_analysis_messages,
    publish_coin_history_loaded_message,
    publish_coin_history_progress_message,
)

PersistenceBoundary = AsyncSession | BaseAsyncUnitOfWork


def _session_from_boundary(boundary: PersistenceBoundary):
    return boundary.session if hasattr(boundary, "session") else boundary


async def _commit_boundary(boundary: PersistenceBoundary) -> None:
    await boundary.commit()


def _normalized_coin_values(payload: CoinCreate) -> dict[str, Any]:
    return {
        "symbol": payload.symbol.strip().upper(),
        "name": payload.name.strip(),
        "asset_type": payload.asset_type.strip().lower(),
        "theme": payload.theme.strip().lower(),
        "sector_code": (payload.sector or payload.theme).strip().lower(),
        "source": payload.source.strip().lower(),
        "enabled": payload.enabled,
        "sort_order": payload.sort_order,
        "candles_config": market_data_support.serialize_candles(payload.candles),
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
    db: AsyncSession,
    payload: CoinCreate,
) -> Coin:
    coins = CoinRepository(db)
    metrics = CoinMetricsRepository(db)
    existing = await coins.get_by_symbol(payload.symbol, include_deleted=True)
    normalized = _normalized_coin_values(payload)

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
    db: AsyncSession,
    coin: Coin,
) -> None:
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
    db: AsyncSession,
    coin: Coin,
    payload,
) -> PriceHistoryReadModel:
    resolved_interval = market_data_support.resolve_history_interval(coin, payload.interval)
    base_interval = str(market_data_support.get_base_candle_config(coin)["interval"])
    if resolved_interval != base_interval:
        raise ValueError(f"Manual history writes are only supported for the {base_interval} base timeframe.")

    timeframe = market_data_repos.interval_to_timeframe(resolved_interval)
    timestamp = market_data_repos.align_timeframe_timestamp(payload.timestamp, timeframe)
    close = float(payload.price)
    volume = float(payload.volume) if payload.volume is not None else None
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
    market_data_support.publish_candle_events(
        coin_id=int(coin.id),
        timeframe=timeframe,
        timestamp=timestamp,
        created_count=1,
        source="manual",
    )
    return price_history_read_model(
        coin_id=int(coin.id),
        interval=resolved_interval,
        timestamp=timestamp,
        price=close,
        volume=volume,
    )


async def _sync_watched_assets_async_internal(
    db: AsyncSession,
) -> list[str]:
    coins = CoinRepository(db)
    metrics = CoinMetricsRepository(db)
    for raw_asset in WATCHED_ASSETS:
        asset = CoinCreate(
            symbol=str(raw_asset["symbol"]),
            name=str(raw_asset["name"]),
            asset_type=str(raw_asset["asset_type"]),
            theme=str(raw_asset["theme"]),
            source=str(raw_asset["source"]),
            enabled=bool(raw_asset["enabled"]),
            sort_order=int(raw_asset["order"]),
            candles=[CandleConfig.model_validate(candle) for candle in raw_asset["candles"]],
        )
        existing = await coins.get_by_symbol(asset.symbol, include_deleted=True)
        if existing is not None and existing.deleted_at is not None:
            continue
        if existing is None:
            created = await _create_or_update_coin_async(db, asset)
            await metrics.ensure_row(int(created.id))
            continue

        normalized = _normalized_coin_values(asset)
        sync_settings_changed = (
            existing.asset_type != normalized["asset_type"]
            or existing.source != normalized["source"]
            or existing.candles_config != normalized["candles_config"]
        )
        was_deleted = existing.deleted_at is not None
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
    return [coin.symbol for coin in await CoinRepository(db).list()]


class MarketDataService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._coins = CoinRepository(uow.session)

    async def create_coin(self, payload: CoinCreate) -> CoinReadModel:
        coin = await _create_or_update_coin_async(self._uow.session, payload)
        await self._uow.commit()
        await self._coins.refresh(coin)
        return await _coin_read_after_write(self._uow.session, coin, include_deleted=True)

    async def delete_coin(self, symbol: str) -> bool:
        coin = await self._coins.get_for_update_by_symbol(symbol)
        if coin is None:
            return False
        await _delete_coin_async(self._uow.session, coin)
        await self._uow.commit()
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
        item = await _create_price_history_async_internal(self._uow.session, coin, payload)
        await self._uow.commit()
        return item

    async def sync_watched_assets(self) -> list[str]:
        items = await _sync_watched_assets_async_internal(self._uow.session)
        await self._uow.commit()
        return items


class MarketDataHistorySyncService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._coins = CoinRepository(uow.session)

    async def sync_coin_history_backfill(
        self,
        *,
        symbol: str,
        force: bool = False,
    ) -> dict[str, int | str]:
        coin = await self._coins.get_for_update_by_symbol(symbol)
        if coin is None:
            return {"status": "error", "symbol": symbol.strip().upper(), "reason": "coin_not_found"}
        return await _sync_coin_history_async(self._uow, coin, history_mode="backfill", force=force)

    async def sync_coin_latest_history(
        self,
        *,
        symbol: str,
        force: bool = False,
    ) -> dict[str, int | str]:
        coin = await self._coins.get_for_update_by_symbol(symbol)
        if coin is None:
            return {"status": "error", "symbol": symbol.strip().upper(), "reason": "coin_not_found"}
        if coin.history_backfill_completed_at is None:
            return {"symbol": coin.symbol, "created": 0, "status": "pending_backfill"}
        return await _sync_coin_history_async(self._uow, coin, history_mode="latest", force=force)


async def _get_latest_candle_timestamp_async(
    db: AsyncSession,
    *,
    coin_id: int,
    timeframe: int,
) -> datetime | None:
    return await CandleRepository(db).get_latest_timestamp(coin_id=coin_id, timeframe=timeframe)


async def _coin_has_base_candles_async(db: AsyncSession, coin: Coin) -> bool:
    return (
        await _get_latest_candle_timestamp_async(
            db,
            coin_id=int(coin.id),
            timeframe=market_data_support.get_coin_base_timeframe(coin),
        )
    ) is not None


async def _ensure_coin_metrics_row_async(db: AsyncSession, coin_id: int) -> None:
    await CoinMetricsRepository(db).ensure_row(coin_id)


async def _refresh_continuous_aggregate_range_async(
    *,
    timeframe: int,
    window_start: datetime,
    window_end: datetime,
) -> None:
    await TimescaleContinuousAggregateRepository(async_engine).refresh_range(
        timeframe=timeframe,
        window_start=window_start,
        window_end=window_end,
    )


async def _calculate_backfill_progress_async(
    db: AsyncSession,
    *,
    coin_id: int,
    candles: Sequence[dict[str, Any]],
    reference_time: datetime,
) -> tuple[int, int, float]:
    del candles
    coin = await CoinRepository(db).get_by_id(int(coin_id))
    if coin is None:
        return 0, 0, 0.0
    base_candle = market_data_support.get_base_candle_config(coin)
    interval = market_data_domain.normalize_interval(str(base_candle["interval"]))
    retention_bars = max(int(base_candle["retention_bars"]), 1)
    latest_available = market_data_domain.latest_completed_timestamp(interval, reference_time)
    window_start = market_data_domain.history_window_start(latest_available, interval, retention_bars)
    total_points = retention_bars
    loaded_points = min(
        await CandleRepository(db).count_rows_between(
            coin_id=int(coin.id),
            timeframe=market_data_repos.interval_to_timeframe(interval),
            window_start=window_start,
            window_end=latest_available,
        ),
        retention_bars,
    )
    progress_percent = min((loaded_points / total_points) * 100, 100.0)
    return loaded_points, total_points, round(progress_percent, 1)


async def _prune_future_price_history_async(
    boundary: PersistenceBoundary,
    *,
    coin_id: int,
    interval: str,
    latest_allowed: datetime,
) -> int:
    db = _session_from_boundary(boundary)
    resolved_interval = market_data_domain.normalize_interval(interval)
    timeframe = market_data_repos.interval_to_timeframe(resolved_interval)
    count = await CandleRepository(db).delete_future_rows(
        coin_id=coin_id,
        timeframe=timeframe,
        latest_allowed=latest_allowed,
    )
    await _commit_boundary(boundary)
    return count


async def _prune_price_history_async(
    boundary: PersistenceBoundary,
    *,
    coin_id: int,
    interval: str,
    retention_bars: int,
) -> int:
    db = _session_from_boundary(boundary)
    latest_timestamp = await _get_latest_history_timestamp_async(db, coin_id=coin_id, interval=interval)
    if latest_timestamp is None:
        return 0
    cutoff = market_data_domain.history_window_start(
        latest_timestamp,
        market_data_domain.normalize_interval(interval),
        retention_bars,
    )
    timeframe = market_data_repos.interval_to_timeframe(market_data_domain.normalize_interval(interval))
    count = await CandleRepository(db).delete_rows_before(
        coin_id=coin_id,
        timeframe=timeframe,
        cutoff=cutoff,
    )
    await _commit_boundary(boundary)
    return count


async def _get_latest_history_timestamp_async(
    db: AsyncSession,
    *,
    coin_id: int,
    interval: str,
) -> datetime | None:
    return await CandleRepository(db).get_latest_timestamp(
        coin_id=coin_id,
        timeframe=market_data_repos.interval_to_timeframe(market_data_domain.normalize_interval(interval)),
    )


async def _upsert_base_candles_async(
    boundary: PersistenceBoundary,
    *,
    coin_id: int,
    interval: str,
    bars,
) -> datetime | None:
    db = _session_from_boundary(boundary)
    coin = await CoinRepository(db).get_by_id(int(coin_id))
    if coin is None or not bars:
        return None
    timeframe = market_data_repos.interval_to_timeframe(interval)
    latest_existing = await _get_latest_candle_timestamp_async(db, coin_id=int(coin.id), timeframe=timeframe)
    rows = [
        {
            "coin_id": int(coin.id),
            "timeframe": timeframe,
            "timestamp": market_data_domain.ensure_utc(bar.timestamp),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume) if bar.volume is not None else None,
        }
        for bar in bars
    ]
    candles = CandleRepository(db)
    for offset in range(0, len(rows), 2000):
        await candles.upsert_rows(rows[offset : offset + 2000])
    await _commit_boundary(boundary)

    earliest_incoming = min(market_data_domain.ensure_utc(bar.timestamp) for bar in bars)
    latest_incoming = max(market_data_domain.ensure_utc(bar.timestamp) for bar in bars)
    if timeframe == market_data_repos.BASE_TIMEFRAME_MINUTES:
        for aggregate_timeframe in market_data_repos.AGGREGATE_VIEW_BY_TIMEFRAME:
            await _refresh_continuous_aggregate_range_async(
                timeframe=aggregate_timeframe,
                window_start=earliest_incoming,
                window_end=latest_incoming,
            )
    if latest_existing is None or latest_incoming > latest_existing:
        return latest_incoming
    return None


async def _sync_coin_history_async(
    boundary: PersistenceBoundary,
    coin: Coin,
    *,
    history_mode: str,
    force: bool = False,
) -> dict[str, int | str]:
    db = _session_from_boundary(boundary)
    if coin.deleted_at is not None or not coin.enabled:
        return {"symbol": coin.symbol, "created": 0, "status": "skipped"}

    now = market_data_domain.utc_now()
    if not force and coin.next_history_sync_at is not None and coin.next_history_sync_at > now:
        return {
            "symbol": coin.symbol,
            "created": 0,
            "status": "deferred",
            "retry_at": coin.next_history_sync_at.isoformat(),
        }

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
        boundary,
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
        latest_candle_timestamp = await _upsert_base_candles_async(
            boundary,
            coin_id=int(coin.id),
            interval=interval,
            bars=fetch_result.bars,
        )
        total_created += len(fetch_result.bars)
        if latest_candle_timestamp is not None:
            market_data_support.publish_candle_events(
                coin_id=int(coin.id),
                timeframe=market_data_repos.interval_to_timeframe(interval),
                timestamp=latest_candle_timestamp,
                created_count=len(fetch_result.bars),
                source=history_mode,
            )
        await _prune_price_history_async(
            boundary,
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
            coin.last_history_sync_at = now
            coin.next_history_sync_at = now + timedelta(hours=1)
            coin.last_history_sync_error = (fetch_result.error or "Market source carousel exhausted.")[:255]
            await _commit_boundary(boundary)
            await CoinRepository(db).refresh(coin)
            return {
                "symbol": coin.symbol,
                "created": total_created,
                "status": "backoff",
                "retry_at": coin.next_history_sync_at.isoformat(),
                "reason": str(coin.last_history_sync_error),
            }
    else:
        await _prune_price_history_async(
            boundary,
            coin_id=int(coin.id),
            interval=interval,
            retention_bars=retention_bars,
        )

    if history_mode == "backfill":
        coin.history_backfill_completed_at = now
    coin.last_history_sync_at = now
    coin.next_history_sync_at = None
    coin.last_history_sync_error = None
    await _commit_boundary(boundary)
    await CoinRepository(db).refresh(coin)

    if history_mode == "backfill":
        loaded_points, total_points, _ = await _calculate_backfill_progress_async(
            db,
            coin_id=int(coin.id),
            candles=candles,
            reference_time=now,
        )
        if last_progress_percent != 100.0:
            publish_coin_history_progress_message(
                coin,
                progress_percent=100.0,
                loaded_points=loaded_points,
                total_points=total_points,
            )
        publish_coin_history_loaded_message(coin, total_points=total_points)
        publish_coin_analysis_messages(coin)

    return {"symbol": coin.symbol, "created": total_created, "status": "ok"}


__all__ = ["MarketDataHistorySyncService", "MarketDataService"]
