from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import AsyncSessionLocal, async_engine
from app.core.watched_assets import WATCHED_ASSETS
from app.apps.market_data.schemas import CandleConfig, CoinCreate
from app.apps.market_data.models import Candle, Coin
from app.apps.indicators.models import CoinMetrics, IndicatorCache
from app.apps.signals.models import Signal
from app.apps.market_data.repos import (
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
from app.apps.market_data.service_layer import (
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
from app.apps.market_data.domain import (
    align_timestamp,
    ensure_utc,
    history_window_start,
    interval_delta,
    latest_completed_timestamp,
    normalize_interval,
    utc_now,
)
from app.runtime.streams.messages import (
    publish_coin_analysis_messages,
    publish_coin_history_loaded_message,
    publish_coin_history_progress_message,
)
from app.apps.market_data.sources import get_market_source_carousel


async def get_coin_by_symbol_async(
    db: AsyncSession,
    symbol: str,
    *,
    include_deleted: bool = False,
) -> Coin | None:
    stmt: Select[tuple[Coin]] = select(Coin).where(Coin.symbol == symbol.upper())
    if not include_deleted:
        stmt = stmt.where(Coin.deleted_at.is_(None))
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_coins_async(
    db: AsyncSession,
    *,
    enabled_only: bool = False,
    include_deleted: bool = False,
) -> Sequence[Coin]:
    stmt: Select[tuple[Coin]] = select(Coin)
    if not include_deleted:
        stmt = stmt.where(Coin.deleted_at.is_(None))
    if enabled_only:
        stmt = stmt.where(Coin.enabled.is_(True))
    stmt = stmt.order_by(Coin.sort_order.asc(), Coin.symbol.asc())
    return (await db.execute(stmt)).scalars().all()


async def _get_latest_candle_timestamp_async(
    db: AsyncSession,
    *,
    coin_id: int,
    timeframe: int,
) -> datetime | None:
    return (
        await db.execute(
            select(Candle.timestamp)
            .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _coin_has_base_candles_async(db: AsyncSession, coin: Coin) -> bool:
    return (
        await _get_latest_candle_timestamp_async(
            db,
            coin_id=int(coin.id),
            timeframe=get_coin_base_timeframe(coin),
        )
    ) is not None


async def _ensure_coin_metrics_row_async(db: AsyncSession, coin_id: int) -> None:
    stmt = insert(CoinMetrics).values({"coin_id": coin_id, "updated_at": utc_now()})
    stmt = stmt.on_conflict_do_nothing(index_elements=["coin_id"])
    await db.execute(stmt)


async def _refresh_continuous_aggregate_range_async(
    *,
    timeframe: int,
    window_start: datetime,
    window_end: datetime,
) -> None:
    if timeframe not in AGGREGATE_VIEW_BY_TIMEFRAME:
        return
    aligned_start = align_timeframe_timestamp(window_start, timeframe)
    aligned_end = align_timeframe_timestamp(window_end, timeframe) + timeframe_delta(timeframe)
    async with async_engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await connection.execute(
            text("CALL refresh_continuous_aggregate(:view_name, :window_start, :window_end)"),
            {
                "view_name": AGGREGATE_VIEW_BY_TIMEFRAME[timeframe],
                "window_start": aligned_start,
                "window_end": aligned_end,
            },
        )


async def create_coin_async(db: AsyncSession, payload: CoinCreate) -> Coin:
    existing = await get_coin_by_symbol_async(db, payload.symbol, include_deleted=True)
    candles = serialize_candles(payload.candles)
    normalized_name = payload.name.strip()
    normalized_asset_type = payload.asset_type.strip().lower()
    normalized_theme = payload.theme.strip().lower()
    normalized_sector = (payload.sector or payload.theme).strip().lower()
    normalized_source = payload.source.strip().lower()

    if existing is not None:
        was_deleted = existing.deleted_at is not None
        sync_settings_changed = (
            existing.asset_type != normalized_asset_type
            or existing.source != normalized_source
            or existing.candles_config != candles
        )
        existing.name = normalized_name
        existing.asset_type = normalized_asset_type
        existing.theme = normalized_theme
        existing.sector_code = normalized_sector
        existing.source = normalized_source
        existing.enabled = payload.enabled
        existing.sort_order = payload.sort_order
        existing.candles_config = candles
        existing.deleted_at = None
        if was_deleted or sync_settings_changed:
            existing.history_backfill_completed_at = None
            existing.last_history_sync_at = None
            existing.next_history_sync_at = None
            existing.last_history_sync_error = None
        await _ensure_coin_metrics_row_async(db, int(existing.id))
        await db.commit()
        await db.refresh(existing)
        return existing

    coin = Coin(
        symbol=payload.symbol.upper(),
        name=normalized_name,
        asset_type=normalized_asset_type,
        theme=normalized_theme,
        sector_code=normalized_sector,
        source=normalized_source,
        enabled=payload.enabled,
        sort_order=payload.sort_order,
        candles_config=candles,
    )
    db.add(coin)
    await db.flush()
    await _ensure_coin_metrics_row_async(db, int(coin.id))
    await db.commit()
    await db.refresh(coin)
    return coin


async def delete_coin_async(db: AsyncSession, coin: Coin) -> None:
    await db.execute(delete(Candle).where(Candle.coin_id == coin.id))
    await db.execute(delete(IndicatorCache).where(IndicatorCache.coin_id == coin.id))
    await db.execute(delete(Signal).where(Signal.coin_id == coin.id))
    await db.execute(delete(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
    coin.enabled = False
    coin.deleted_at = utc_now()
    coin.history_backfill_completed_at = None
    coin.last_history_sync_at = None
    coin.next_history_sync_at = None
    coin.last_history_sync_error = None
    await db.commit()


async def list_price_history_async(
    db: AsyncSession,
    symbol: str,
    interval: str | None = None,
) -> Sequence[dict[str, Any]]:
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        return []
    resolved_interval = resolve_history_interval(coin, interval)
    timeframe = interval_to_timeframe(resolved_interval)
    retention_bars = get_interval_retention_bars(coin, resolved_interval)
    rows = (
        await db.execute(
            select(Candle.timestamp, Candle.close, Candle.volume)
            .where(Candle.coin_id == coin.id, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(max(retention_bars, 1))
        )
    ).all()
    return [
        {
            "coin_id": int(coin.id),
            "interval": resolved_interval,
            "timestamp": row.timestamp,
            "price": float(row.close),
            "volume": float(row.volume) if row.volume is not None else None,
        }
        for row in reversed(rows)
    ]


async def create_price_history_async(
    db: AsyncSession,
    coin: Coin,
    payload,
) -> dict[str, Any]:
    resolved_interval = resolve_history_interval(coin, payload.interval)
    base_interval = str(get_base_candle_config(coin)["interval"])
    if resolved_interval != base_interval:
        raise ValueError(f"Manual history writes are only supported for the {base_interval} base timeframe.")

    timeframe = interval_to_timeframe(resolved_interval)
    timestamp = align_timeframe_timestamp(payload.timestamp, timeframe)
    close = float(payload.price)
    volume = float(payload.volume) if payload.volume is not None else None
    stmt = insert(Candle).values(
        {
            "coin_id": coin.id,
            "timeframe": timeframe,
            "timestamp": timestamp,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": volume,
        }
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["coin_id", "timeframe", "timestamp"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    await db.execute(stmt)
    await db.commit()
    publish_candle_events(
        coin_id=int(coin.id),
        timeframe=timeframe,
        timestamp=timestamp,
        created_count=1,
        source="manual",
    )
    return {
        "coin_id": int(coin.id),
        "interval": resolved_interval,
        "timestamp": timestamp,
        "price": close,
        "volume": volume,
    }


async def get_next_pending_backfill_due_at_async() -> datetime | None:
    async with AsyncSessionLocal() as db:
        now = utc_now()
        coins = (
            await db.execute(
                select(Coin)
                .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
                .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
            )
        ).scalars().all()
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
    result: list[str] = []
    for coin in coins:
        if coin.history_backfill_completed_at is None or not await _coin_has_base_candles_async(db, coin):
            result.append(coin.symbol)
    return result


async def list_coin_symbols_ready_for_latest_sync_async(db: AsyncSession) -> list[str]:
    coins = (
        await db.execute(
            select(Coin)
            .where(
                Coin.deleted_at.is_(None),
                Coin.enabled.is_(True),
                Coin.history_backfill_completed_at.is_not(None),
            )
            .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
        )
    ).scalars().all()
    result: list[str] = []
    for coin in coins:
        if await _coin_has_base_candles_async(db, coin):
            result.append(coin.symbol)
    return result


async def sync_watched_assets_async(db: AsyncSession) -> list[str]:
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
        existing = await get_coin_by_symbol_async(db, asset.symbol, include_deleted=True)
        if existing is not None and existing.deleted_at is not None:
            continue
        if existing is None:
            await create_coin_async(db, asset)
            continue
        candles = serialize_candles(asset.candles)
        sync_settings_changed = (
            existing.asset_type != asset.asset_type.strip().lower()
            or existing.source != asset.source.strip().lower()
            or existing.candles_config != candles
        )
        was_deleted = existing.deleted_at is not None
        existing.name = asset.name.strip()
        existing.asset_type = asset.asset_type.strip().lower()
        existing.theme = asset.theme.strip().lower()
        existing.sector_code = (asset.sector or asset.theme).strip().lower()
        existing.source = asset.source.strip().lower()
        existing.enabled = asset.enabled
        existing.sort_order = asset.sort_order
        existing.candles_config = candles
        existing.deleted_at = None
        if was_deleted or sync_settings_changed:
            existing.history_backfill_completed_at = None
            existing.last_history_sync_at = None
            existing.next_history_sync_at = None
            existing.last_history_sync_error = None
        await db.commit()
    return [coin.symbol for coin in await list_coins_async(db)]


async def _calculate_backfill_progress_async(
    db: AsyncSession,
    *,
    coin_id: int,
    candles: Sequence[dict[str, Any]],
    reference_time: datetime,
) -> tuple[int, int, float]:
    del candles
    coin = await db.get(Coin, int(coin_id))
    if coin is None:
        return 0, 0, 0.0
    base_candle = get_base_candle_config(coin)
    interval = normalize_interval(str(base_candle["interval"]))
    retention_bars = max(int(base_candle["retention_bars"]), 1)
    latest_available = latest_completed_timestamp(interval, reference_time)
    window_start = history_window_start(latest_available, interval, retention_bars)
    total_points = retention_bars
    loaded_points = min(
        int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Candle)
                    .where(
                        Candle.coin_id == coin.id,
                        Candle.timeframe == interval_to_timeframe(interval),
                        Candle.timestamp >= window_start,
                        Candle.timestamp <= latest_available,
                    )
                )
            ).scalar_one()
            or 0
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
    result = await db.execute(
        delete(Candle).where(
            Candle.coin_id == coin_id,
            Candle.timeframe == timeframe,
            Candle.timestamp > latest_allowed,
        )
    )
    await db.commit()
    return int(result.rowcount or 0)


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
    result = await db.execute(
        delete(Candle).where(
            Candle.coin_id == coin_id,
            Candle.timeframe == timeframe,
            Candle.timestamp < cutoff,
        )
    )
    await db.commit()
    return int(result.rowcount or 0)


async def _get_latest_history_timestamp_async(
    db: AsyncSession,
    *,
    coin_id: int,
    interval: str,
) -> datetime | None:
    resolved_interval = normalize_interval(interval)
    timeframe = interval_to_timeframe(resolved_interval)
    return (
        await db.execute(
            select(Candle.timestamp)
            .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _upsert_base_candles_async(
    db: AsyncSession,
    *,
    coin_id: int,
    interval: str,
    bars,
) -> datetime | None:
    coin = await db.get(Coin, int(coin_id))
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
    for offset in range(0, len(rows), 2000):
        chunk = rows[offset : offset + 2000]
        stmt = insert(Candle).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe", "timestamp"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        await db.execute(stmt)
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
            await db.refresh(coin)
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
    await db.refresh(coin)

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
