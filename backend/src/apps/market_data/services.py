from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.market_data.domain import (
    align_timestamp,
    ensure_utc,
    history_window_start,
    interval_delta,
    latest_completed_timestamp,
    normalize_interval,
    utc_now,
)
from src.apps.market_data.models import Coin
from src.apps.market_data.query_services import MarketDataQueryService
from src.apps.market_data.read_models import (
    CoinReadModel,
    PriceHistoryReadModel,
    coin_read_model_from_orm,
    price_history_read_model,
)
from src.apps.market_data.repos import (
    AGGREGATE_VIEW_BY_TIMEFRAME,
    BASE_TIMEFRAME_MINUTES,
    CandlePoint,
    align_timeframe_timestamp,
    candle_close_timestamp,
    fetch_candle_points,
    fetch_candle_points_between,
    get_latest_candle_timestamp,
    interval_to_timeframe,
    timeframe_delta,
    upsert_base_candles,
)
from src.apps.market_data.repositories import (
    CandleRepository,
    CoinMetricsRepository,
    CoinRepository,
    IndicatorCacheRepository,
    SignalRepository,
    TimescaleContinuousAggregateRepository,
)
from src.apps.market_data.schemas import CandleConfig, CoinCreate
from src.apps.market_data.service_layer import (
    calculate_backfill_progress,
    coin_has_base_candles,
    count_candle_points,
    count_price_history_points,
    create_coin,
    create_price_history,
    delete_coin,
    get_base_candle_config,
    get_coin_base_timeframe,
    get_coin_by_id,
    get_coin_by_symbol,
    get_interval_retention_bars,
    get_latest_history_timestamp,
    get_latest_price,
    get_next_pending_backfill_due_at,
    list_coins_pending_backfill,
    list_coins_ready_for_latest_sync,
    list_price_history,
    prune_future_price_history,
    prune_price_history,
    publish_candle_events,
    resolve_history_interval,
    serialize_candles,
    sync_watched_assets,
)
from src.apps.market_data.sources import get_market_source_carousel
from src.core.db.session import AsyncSessionLocal, async_engine
from src.core.db.uow import BaseAsyncUnitOfWork
from src.core.watched_assets import WATCHED_ASSETS
from src.runtime.streams.messages import (
    publish_coin_analysis_messages,
    publish_coin_history_loaded_message,
    publish_coin_history_progress_message,
)


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
        "candles_config": serialize_candles(payload.candles),
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
    *,
    commit: bool = True,
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
        if commit:
            await db.commit()
            await coins.refresh(existing)
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
    if commit:
        await db.commit()
        await coins.refresh(coin)
    return coin


async def _delete_coin_async(
    db: AsyncSession,
    coin: Coin,
    *,
    commit: bool = True,
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
    coin.deleted_at = utc_now()
    _reset_history_sync_state(coin)
    if commit:
        await db.commit()


async def _create_price_history_async_internal(
    db: AsyncSession,
    coin: Coin,
    payload,
    *,
    commit: bool = True,
) -> PriceHistoryReadModel:
    resolved_interval = resolve_history_interval(coin, payload.interval)
    base_interval = str(get_base_candle_config(coin)["interval"])
    if resolved_interval != base_interval:
        raise ValueError(f"Manual history writes are only supported for the {base_interval} base timeframe.")

    timeframe = interval_to_timeframe(resolved_interval)
    timestamp = align_timeframe_timestamp(payload.timestamp, timeframe)
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
    if commit:
        await db.commit()
    publish_candle_events(
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
    *,
    commit: bool = True,
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
            created = await _create_or_update_coin_async(db, asset, commit=False)
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

    if commit:
        await db.commit()
    return [coin.symbol for coin in await CoinRepository(db).list()]


class MarketDataService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._coins = CoinRepository(uow.session)

    async def create_coin(self, payload: CoinCreate) -> CoinReadModel:
        coin = await _create_or_update_coin_async(self._uow.session, payload, commit=False)
        await self._uow.commit()
        await self._coins.refresh(coin)
        return await _coin_read_after_write(self._uow.session, coin, include_deleted=True)

    async def delete_coin(self, symbol: str) -> bool:
        coin = await self._coins.get_for_update_by_symbol(symbol)
        if coin is None:
            return False
        await _delete_coin_async(self._uow.session, coin, commit=False)
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
        item = await _create_price_history_async_internal(self._uow.session, coin, payload, commit=False)
        await self._uow.commit()
        return item

    async def sync_watched_assets(self) -> list[str]:
        items = await _sync_watched_assets_async_internal(self._uow.session, commit=False)
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
        if force:
            return await sync_coin_history_backfill_forced_async(self._uow.session, coin)
        return await sync_coin_history_backfill_async(self._uow.session, coin)

    async def sync_coin_latest_history(
        self,
        *,
        symbol: str,
        force: bool = False,
    ) -> dict[str, int | str]:
        coin = await self._coins.get_for_update_by_symbol(symbol)
        if coin is None:
            return {"status": "error", "symbol": symbol.strip().upper(), "reason": "coin_not_found"}
        return await sync_coin_latest_history_async(self._uow.session, coin, force=force)


async def get_coin_by_symbol_async(
    db: AsyncSession,
    symbol: str,
    *,
    include_deleted: bool = False,
) -> Coin | None:
    return await CoinRepository(db).get_by_symbol(symbol, include_deleted=include_deleted)


async def list_coins_async(
    db: AsyncSession,
    *,
    enabled_only: bool = False,
    include_deleted: bool = False,
) -> Sequence[Coin]:
    return await CoinRepository(db).list(enabled_only=enabled_only, include_deleted=include_deleted)


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
            timeframe=get_coin_base_timeframe(coin),
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


async def create_coin_async(db: AsyncSession, payload: CoinCreate) -> Coin:
    return await _create_or_update_coin_async(db, payload, commit=True)


async def delete_coin_async(db: AsyncSession, coin: Coin) -> None:
    await _delete_coin_async(db, coin, commit=True)


async def list_price_history_async(
    db: AsyncSession,
    symbol: str,
    interval: str | None = None,
) -> Sequence[dict[str, Any]]:
    items = await MarketDataQueryService(db).list_price_history(symbol, interval)
    return [
        {
            "coin_id": item.coin_id,
            "interval": item.interval,
            "timestamp": item.timestamp,
            "price": item.price,
            "volume": item.volume,
        }
        for item in items
    ]


async def create_price_history_async(
    db: AsyncSession,
    coin: Coin,
    payload,
) -> dict[str, Any]:
    item = await _create_price_history_async_internal(db, coin, payload, commit=True)
    return {
        "coin_id": item.coin_id,
        "interval": item.interval,
        "timestamp": item.timestamp,
        "price": item.price,
        "volume": item.volume,
    }


async def get_next_pending_backfill_due_at_async() -> datetime | None:
    async with AsyncSessionLocal() as db:
        now = utc_now()
        coins = (
            (
                await db.execute(
                    select(Coin)
                    .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
                    .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
                )
            )
            .scalars()
            .all()
        )
        pending_due_at: list[datetime] = []
        for coin in coins:
            if coin.history_backfill_completed_at is None or not await _coin_has_base_candles_async(db, coin):
                if coin.next_history_sync_at is None or coin.next_history_sync_at <= now:
                    return now
                pending_due_at.append(coin.next_history_sync_at)
        return min(pending_due_at) if pending_due_at else None


async def list_coin_symbols_pending_backfill_async(
    db: AsyncSession,
    *,
    symbol: str | None = None,
) -> list[str]:
    stmt: Select[tuple[Coin]] = (
        select(Coin)
        .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
        .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    coins = (await db.execute(stmt)).scalars().all()
    return [
        coin.symbol
        for coin in coins
        if coin.history_backfill_completed_at is None or not await _coin_has_base_candles_async(db, coin)
    ]


async def list_coin_symbols_ready_for_latest_sync_async(db: AsyncSession) -> list[str]:
    coins = (
        (
            await db.execute(
                select(Coin)
                .where(
                    Coin.deleted_at.is_(None),
                    Coin.enabled.is_(True),
                    Coin.history_backfill_completed_at.is_not(None),
                )
                .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
            )
        )
        .scalars()
        .all()
    )
    return [coin.symbol for coin in coins if await _coin_has_base_candles_async(db, coin)]


async def sync_watched_assets_async(db: AsyncSession) -> list[str]:
    return await _sync_watched_assets_async_internal(db, commit=True)


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
    base_candle = get_base_candle_config(coin)
    interval = normalize_interval(str(base_candle["interval"]))
    retention_bars = max(int(base_candle["retention_bars"]), 1)
    latest_available = latest_completed_timestamp(interval, reference_time)
    window_start = history_window_start(latest_available, interval, retention_bars)
    total_points = retention_bars
    loaded_points = min(
        await CandleRepository(db).count_rows_between(
            coin_id=int(coin.id),
            timeframe=interval_to_timeframe(interval),
            window_start=window_start,
            window_end=latest_available,
        ),
        retention_bars,
    )
    progress_percent = min((loaded_points / total_points) * 100, 100.0)
    return loaded_points, total_points, round(progress_percent, 1)


async def _prune_future_price_history_async(
    db: AsyncSession,
    *,
    coin_id: int,
    interval: str,
    latest_allowed: datetime,
) -> int:
    resolved_interval = normalize_interval(interval)
    timeframe = interval_to_timeframe(resolved_interval)
    count = await CandleRepository(db).delete_future_rows(
        coin_id=coin_id,
        timeframe=timeframe,
        latest_allowed=latest_allowed,
    )
    await db.commit()
    return count


async def _prune_price_history_async(
    db: AsyncSession,
    *,
    coin_id: int,
    interval: str,
    retention_bars: int,
) -> int:
    latest_timestamp = await _get_latest_history_timestamp_async(db, coin_id=coin_id, interval=interval)
    if latest_timestamp is None:
        return 0
    cutoff = history_window_start(latest_timestamp, normalize_interval(interval), retention_bars)
    timeframe = interval_to_timeframe(normalize_interval(interval))
    count = await CandleRepository(db).delete_rows_before(
        coin_id=coin_id,
        timeframe=timeframe,
        cutoff=cutoff,
    )
    await db.commit()
    return count


async def _get_latest_history_timestamp_async(
    db: AsyncSession,
    *,
    coin_id: int,
    interval: str,
) -> datetime | None:
    return await CandleRepository(db).get_latest_timestamp(
        coin_id=coin_id,
        timeframe=interval_to_timeframe(normalize_interval(interval)),
    )


async def _upsert_base_candles_async(
    db: AsyncSession,
    *,
    coin_id: int,
    interval: str,
    bars,
) -> datetime | None:
    coin = await CoinRepository(db).get_by_id(int(coin_id))
    if coin is None or not bars:
        return None
    timeframe = interval_to_timeframe(interval)
    latest_existing = await _get_latest_candle_timestamp_async(db, coin_id=int(coin.id), timeframe=timeframe)
    rows = [
        {
            "coin_id": int(coin.id),
            "timeframe": timeframe,
            "timestamp": ensure_utc(bar.timestamp),
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
    await db.commit()

    earliest_incoming = min(ensure_utc(bar.timestamp) for bar in bars)
    latest_incoming = max(ensure_utc(bar.timestamp) for bar in bars)
    if timeframe == BASE_TIMEFRAME_MINUTES:
        for aggregate_timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
            await _refresh_continuous_aggregate_range_async(
                timeframe=aggregate_timeframe,
                window_start=earliest_incoming,
                window_end=latest_incoming,
            )
    if latest_existing is None or latest_incoming > latest_existing:
        return latest_incoming
    return None


async def _sync_coin_history_async(
    db: AsyncSession,
    coin: Coin,
    *,
    history_mode: str,
    force: bool = False,
) -> dict[str, int | str]:
    if coin.deleted_at is not None or not coin.enabled:
        return {"symbol": coin.symbol, "created": 0, "status": "skipped"}

    now = utc_now()
    if not force and coin.next_history_sync_at is not None and coin.next_history_sync_at > now:
        return {
            "symbol": coin.symbol,
            "created": 0,
            "status": "deferred",
            "retry_at": coin.next_history_sync_at.isoformat(),
        }

    total_created = 0
    candles = serialize_candles(coin.candles_config or [])
    base_candle = get_base_candle_config(coin)
    interval = normalize_interval(str(base_candle["interval"]))
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

    latest_available = latest_completed_timestamp(interval, now)
    await _prune_future_price_history_async(
        db,
        coin_id=int(coin.id),
        interval=interval,
        latest_allowed=latest_available,
    )
    latest_existing = await _get_latest_history_timestamp_async(db, coin_id=int(coin.id), interval=interval)

    if history_mode == "backfill":
        start = history_window_start(latest_available, interval, retention_bars)
    elif latest_existing is None:
        start = latest_available
    else:
        start = latest_existing + interval_delta(interval)

    if start <= latest_available:
        fetch_result = await carousel.fetch_history_window(coin, interval, start, latest_available)
        latest_candle_timestamp = await _upsert_base_candles_async(
            db,
            coin_id=int(coin.id),
            interval=interval,
            bars=fetch_result.bars,
        )
        total_created += len(fetch_result.bars)
        if latest_candle_timestamp is not None:
            publish_candle_events(
                coin_id=int(coin.id),
                timeframe=interval_to_timeframe(interval),
                timestamp=latest_candle_timestamp,
                created_count=len(fetch_result.bars),
                source=history_mode,
            )
        await _prune_price_history_async(
            db,
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
            await db.commit()
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
            db,
            coin_id=int(coin.id),
            interval=interval,
            retention_bars=retention_bars,
        )

    if history_mode == "backfill":
        coin.history_backfill_completed_at = now
    coin.last_history_sync_at = now
    coin.next_history_sync_at = None
    coin.last_history_sync_error = None
    await db.commit()
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


async def sync_coin_history_backfill_async(db: AsyncSession, coin: Coin) -> dict[str, int | str]:
    return await _sync_coin_history_async(db, coin, history_mode="backfill")


async def sync_coin_history_backfill_forced_async(db: AsyncSession, coin: Coin) -> dict[str, int | str]:
    return await _sync_coin_history_async(db, coin, history_mode="backfill", force=True)


async def sync_coin_latest_history_async(
    db: AsyncSession,
    coin: Coin,
    *,
    force: bool = False,
) -> dict[str, int | str]:
    if coin.history_backfill_completed_at is None:
        return {"symbol": coin.symbol, "created": 0, "status": "pending_backfill"}
    return await _sync_coin_history_async(db, coin, history_mode="latest", force=force)


__all__ = [
    "AGGREGATE_VIEW_BY_TIMEFRAME",
    "BASE_TIMEFRAME_MINUTES",
    "CandlePoint",
    "MarketDataHistorySyncService",
    "MarketDataService",
    "align_timeframe_timestamp",
    "align_timestamp",
    "candle_close_timestamp",
    "coin_has_base_candles",
    "count_candle_points",
    "count_price_history_points",
    "create_coin",
    "create_coin_async",
    "create_price_history",
    "create_price_history_async",
    "delete_coin",
    "delete_coin_async",
    "ensure_utc",
    "fetch_candle_points",
    "fetch_candle_points_between",
    "get_base_candle_config",
    "get_coin_base_timeframe",
    "get_coin_by_id",
    "get_coin_by_symbol",
    "get_coin_by_symbol_async",
    "get_interval_retention_bars",
    "get_latest_candle_timestamp",
    "get_latest_history_timestamp",
    "get_latest_price",
    "get_next_pending_backfill_due_at",
    "get_next_pending_backfill_due_at_async",
    "history_window_start",
    "interval_delta",
    "interval_to_timeframe",
    "latest_completed_timestamp",
    "list_coin_symbols_pending_backfill_async",
    "list_coin_symbols_ready_for_latest_sync_async",
    "list_coins_async",
    "list_coins_pending_backfill",
    "list_coins_ready_for_latest_sync",
    "list_price_history",
    "list_price_history_async",
    "normalize_interval",
    "prune_future_price_history",
    "prune_price_history",
    "publish_candle_events",
    "resolve_history_interval",
    "serialize_candles",
    "sync_coin_history_backfill_async",
    "sync_coin_history_backfill_forced_async",
    "sync_coin_latest_history_async",
    "sync_watched_assets",
    "sync_watched_assets_async",
    "timeframe_delta",
    "upsert_base_candles",
    "utc_now",
]
