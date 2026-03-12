from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.apps.indicators.models import CoinMetrics, IndicatorCache
from src.apps.market_data.domain import (
    history_window_start,
    interval_delta,
    latest_completed_timestamp,
    normalize_interval,
    utc_now,
)
from src.apps.market_data.models import Candle, Coin
from src.apps.market_data.repos import (
    AGGREGATE_VIEW_BY_TIMEFRAME,
    BASE_TIMEFRAME_MINUTES,
    align_timeframe_timestamp,
    fetch_candle_points,
    get_latest_candle_timestamp,
    interval_to_timeframe,
    upsert_base_candles,
)
from src.apps.market_data.schemas import CandleConfig, CoinCreate, PriceHistoryCreate
from src.apps.market_data.sources import get_market_source_carousel
from src.apps.signals.models import Signal
from src.core.watched_assets import WATCHED_ASSETS
from src.runtime.streams.messages import (
    publish_coin_analysis_messages,
    publish_coin_history_loaded_message,
    publish_coin_history_progress_message,
)
from src.runtime.streams.publisher import publish_event

PRICE_HISTORY_UPSERT_BATCH_SIZE = 5000


def ensure_coin_metrics_row(db: Session, coin_id: int) -> None:
    stmt = insert(CoinMetrics).values({"coin_id": coin_id, "updated_at": utc_now(), "indicator_version": 1})
    stmt = stmt.on_conflict_do_nothing(index_elements=["coin_id"])
    db.execute(stmt)


def delete_coin_metrics_row(db: Session, coin_id: int) -> None:
    db.execute(delete(CoinMetrics).where(CoinMetrics.coin_id == coin_id))


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


def get_base_candle_config(coin: Coin) -> dict[str, Any]:
    candles = serialize_candles(coin.candles_config or [])
    if not candles:
        return {"interval": "15m", "retention_bars": 20160}

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


def serialize_candles(candles: Sequence[CandleConfig | dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        CandleConfig.model_validate(candle).model_dump()
        if not isinstance(candle, CandleConfig)
        else candle.model_dump()
        for candle in candles
    ]


def resolve_history_interval(coin: Coin, interval: str | None = None) -> str:
    if interval:
        return normalize_interval(interval)
    return str(get_base_candle_config(coin)["interval"])


def coin_has_base_candles(db: Session, coin: Coin) -> bool:
    return get_latest_candle_timestamp(db, coin.id, get_coin_base_timeframe(coin)) is not None


def get_coin_by_symbol(db: Session, symbol: str, include_deleted: bool = False) -> Coin | None:
    stmt = select(Coin).where(Coin.symbol == symbol.upper())
    if not include_deleted:
        stmt = stmt.where(Coin.deleted_at.is_(None))
    return db.scalar(stmt)


def list_coins(
    db: Session,
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
    return db.scalars(stmt).all()


def list_coins_pending_backfill(db: Session, symbol: str | None = None) -> Sequence[Coin]:
    stmt: Select[tuple[Coin]] = (
        select(Coin)
        .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
        .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    coins = db.scalars(stmt).all()
    return [
        coin
        for coin in coins
        if coin.history_backfill_completed_at is None or not coin_has_base_candles(db, coin)
    ]


def list_coins_ready_for_latest_sync(db: Session) -> Sequence[Coin]:
    stmt: Select[tuple[Coin]] = (
        select(Coin)
        .where(
            Coin.deleted_at.is_(None),
            Coin.enabled.is_(True),
            Coin.history_backfill_completed_at.is_not(None),
        )
        .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
    )
    return [coin for coin in db.scalars(stmt).all() if coin_has_base_candles(db, coin)]


def get_next_pending_backfill_due_at(db: Session) -> datetime | None:
    now = utc_now()
    coins = list_coins_pending_backfill(db)
    if any(coin.next_history_sync_at is None or coin.next_history_sync_at <= now for coin in coins):
        return now

    scheduled = [coin.next_history_sync_at for coin in coins if coin.next_history_sync_at is not None]
    return min(scheduled) if scheduled else None


def create_coin(db: Session, payload: CoinCreate) -> Coin:
    existing = get_coin_by_symbol(db, payload.symbol, include_deleted=True)
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
        ensure_coin_metrics_row(db, existing.id)
        db.commit()
        db.refresh(existing)
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
    db.flush()
    ensure_coin_metrics_row(db, coin.id)
    db.commit()
    db.refresh(coin)
    return coin


def _serialize_history_row(
    *,
    coin_id: int,
    interval: str,
    timestamp: datetime,
    close: float,
    volume: float | None,
) -> dict[str, Any]:
    return {
        "coin_id": coin_id,
        "interval": interval,
        "timestamp": timestamp,
        "price": close,
        "volume": volume,
    }


def list_price_history(db: Session, symbol: str, interval: str | None = None) -> Sequence[dict[str, Any]]:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        return []
    resolved_interval = resolve_history_interval(coin, interval)
    timeframe = interval_to_timeframe(resolved_interval)
    rows = fetch_candle_points(db, coin.id, timeframe, get_interval_retention_bars(coin, resolved_interval))
    return [
        _serialize_history_row(
            coin_id=coin.id,
            interval=resolved_interval,
            timestamp=row.timestamp,
            close=float(row.close),
            volume=float(row.volume) if row.volume is not None else None,
        )
        for row in rows
    ]


def get_latest_price(db: Session, symbol: str, interval: str | None = None) -> dict[str, Any] | None:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        return None
    resolved_interval = resolve_history_interval(coin, interval)
    timeframe = interval_to_timeframe(resolved_interval)
    points = fetch_candle_points(db, coin.id, timeframe, 1)
    if not points:
        return None
    point = points[-1]
    return _serialize_history_row(
        coin_id=coin.id,
        interval=resolved_interval,
        timestamp=point.timestamp,
        close=float(point.close),
        volume=float(point.volume) if point.volume is not None else None,
    )


def create_price_history(
    db: Session,
    coin: Coin,
    payload: PriceHistoryCreate,
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
    db.execute(stmt)
    db.commit()
    publish_candle_events(
        coin_id=coin.id,
        timeframe=timeframe,
        timestamp=timestamp,
        created_count=1,
        source="manual",
    )
    return _serialize_history_row(
        coin_id=coin.id,
        interval=resolved_interval,
        timestamp=timestamp,
        close=close,
        volume=volume,
    )


def bulk_create_price_history(
    db: Session,
    coin: Coin,
    interval: str,
    payloads: Sequence[PriceHistoryCreate],
) -> int:
    if not payloads:
        return 0

    resolved_interval = normalize_interval(interval)
    base_interval = str(get_base_candle_config(coin)["interval"])
    if resolved_interval != base_interval:
        raise ValueError(f"Bulk history writes are only supported for the {base_interval} base timeframe.")

    timeframe = interval_to_timeframe(resolved_interval)

    rows = [
        {
            "coin_id": coin.id,
            "timeframe": timeframe,
            "timestamp": align_timeframe_timestamp(payload.timestamp, timeframe),
            "open": float(payload.price),
            "high": float(payload.price),
            "low": float(payload.price),
            "close": float(payload.price),
            "volume": float(payload.volume) if payload.volume is not None else None,
        }
        for payload in payloads
    ]

    for offset in range(0, len(rows), PRICE_HISTORY_UPSERT_BATCH_SIZE):
        chunk = rows[offset : offset + PRICE_HISTORY_UPSERT_BATCH_SIZE]
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
        db.execute(stmt)
    db.commit()
    latest_timestamp = max(row["timestamp"] for row in rows)
    publish_candle_events(
        coin_id=coin.id,
        timeframe=timeframe,
        timestamp=latest_timestamp,
        created_count=len(rows),
        source="bulk_manual",
    )
    return len(rows)


def get_latest_history_timestamp(db: Session, coin_id: int, interval: str) -> datetime | None:
    resolved_interval = normalize_interval(interval)
    timeframe = interval_to_timeframe(resolved_interval)
    return get_latest_candle_timestamp(db, coin_id, timeframe)


def prune_price_history(db: Session, coin: Coin, interval: str, retention_bars: int) -> int:
    resolved_interval = normalize_interval(interval)
    timeframe = interval_to_timeframe(resolved_interval)

    latest_timestamp = get_latest_candle_timestamp(db, coin.id, timeframe)
    if latest_timestamp is None:
        return 0

    cutoff = history_window_start(latest_timestamp, resolved_interval, retention_bars)
    result = db.execute(
        delete(Candle).where(
            Candle.coin_id == coin.id,
            Candle.timeframe == timeframe,
            Candle.timestamp < cutoff,
        ),
    )
    db.commit()
    return int(result.rowcount or 0)


def prune_future_price_history(db: Session, coin: Coin, interval: str, latest_allowed: datetime) -> int:
    resolved_interval = normalize_interval(interval)
    timeframe = interval_to_timeframe(resolved_interval)

    result = db.execute(
        delete(Candle).where(
            Candle.coin_id == coin.id,
            Candle.timeframe == timeframe,
            Candle.timestamp > latest_allowed,
        ),
    )
    db.commit()
    return int(result.rowcount or 0)


def count_price_history_points(
    db: Session,
    coin_id: int,
    interval: str,
    start: datetime,
    end: datetime,
) -> int:
    resolved_interval = normalize_interval(interval)
    timeframe = interval_to_timeframe(resolved_interval)
    points = fetch_candle_points(db, coin_id, timeframe, get_interval_retention_bars(get_coin_by_id(db, coin_id), resolved_interval))
    return len([point for point in points if start <= point.timestamp <= end])


def get_coin_by_id(db: Session, coin_id: int) -> Coin:
    coin = db.get(Coin, coin_id)
    if coin is None:
        raise ValueError(f"Coin '{coin_id}' was not found.")
    return coin


def count_candle_points(
    db: Session,
    coin_id: int,
    timeframe: int,
    start: datetime,
    end: datetime,
) -> int:
    stmt = select(func.count()).select_from(Candle).where(
        Candle.coin_id == coin_id,
        Candle.timeframe == timeframe,
        Candle.timestamp >= start,
        Candle.timestamp <= end,
    )
    return int(db.scalar(stmt) or 0)


def calculate_backfill_progress(
    db: Session,
    coin: Coin,
    candles: Sequence[dict[str, Any]],
    reference_time: datetime,
) -> tuple[int, int, float]:
    del candles
    base_candle = get_base_candle_config(coin)
    interval = normalize_interval(str(base_candle["interval"]))
    retention_bars = max(int(base_candle["retention_bars"]), 1)
    latest_available = latest_completed_timestamp(interval, reference_time)
    window_start = history_window_start(latest_available, interval, retention_bars)
    total_points = retention_bars
    loaded_points = min(
        count_candle_points(
            db,
            coin.id,
            interval_to_timeframe(interval),
            window_start,
            latest_available,
        ),
        retention_bars,
    )

    progress_percent = min((loaded_points / total_points) * 100, 100.0)
    return loaded_points, total_points, round(progress_percent, 1)


def sync_watched_assets(db: Session) -> list[Coin]:
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

        existing = get_coin_by_symbol(db, asset.symbol, include_deleted=True)
        if existing is not None and existing.deleted_at is not None:
            continue
        create_coin(db, asset)

    return list(list_coins(db))


def _sync_coin_history(
    db: Session,
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
        loaded_points, total_points, progress_percent = calculate_backfill_progress(db, coin, candles, now)
        publish_coin_history_progress_message(
            coin,
            progress_percent=progress_percent,
            loaded_points=loaded_points,
            total_points=total_points,
        )
        last_progress_percent = progress_percent

    latest_available = latest_completed_timestamp(interval, now)
    prune_future_price_history(db, coin, interval, latest_available)
    latest_existing = get_latest_history_timestamp(db, coin.id, interval)

    if history_mode == "backfill":
        start = history_window_start(latest_available, interval, retention_bars)
    elif latest_existing is None:
        start = latest_available
    else:
        start = latest_existing + interval_delta(interval)

    if start <= latest_available:
        # NOTE:
        # This legacy synchronous history path remains available intentionally
        # for non-async maintenance/test code. Runtime orchestration uses the
        # async market-data facade instead of this bridge.
        fetch_result = asyncio.run(carousel.fetch_history_window(coin, interval, start, latest_available))
        latest_candle_timestamp = upsert_base_candles(db, coin, interval, fetch_result.bars)
        total_created += len(fetch_result.bars)
        if latest_candle_timestamp is not None:
            publish_candle_events(
                coin_id=coin.id,
                timeframe=interval_to_timeframe(interval),
                timestamp=latest_candle_timestamp,
                created_count=len(fetch_result.bars),
                source=history_mode,
            )
        prune_price_history(db, coin, interval, retention_bars)

        if history_mode == "backfill":
            loaded_points, total_points, progress_percent = calculate_backfill_progress(db, coin, candles, now)
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
            db.commit()
            db.refresh(coin)
            return {
                "symbol": coin.symbol,
                "created": total_created,
                "status": "backoff",
                "retry_at": coin.next_history_sync_at.isoformat(),
                "reason": coin.last_history_sync_error,
            }
    else:
        prune_price_history(db, coin, interval, retention_bars)

    if history_mode == "backfill":
        coin.history_backfill_completed_at = now
    coin.last_history_sync_at = now
    coin.next_history_sync_at = None
    coin.last_history_sync_error = None
    db.commit()
    db.refresh(coin)
    if history_mode == "backfill":
        loaded_points, total_points, _ = calculate_backfill_progress(db, coin, candles, now)
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


def sync_coin_history_backfill(db: Session, coin: Coin) -> dict[str, int | str]:
    return _sync_coin_history(db, coin, history_mode="backfill")


def sync_coin_history_backfill_forced(db: Session, coin: Coin) -> dict[str, int | str]:
    return _sync_coin_history(db, coin, history_mode="backfill", force=True)


def sync_coin_latest_history(db: Session, coin: Coin, *, force: bool = False) -> dict[str, int | str]:
    if coin.history_backfill_completed_at is None:
        return {"symbol": coin.symbol, "created": 0, "status": "pending_backfill"}
    return _sync_coin_history(db, coin, history_mode="latest", force=force)


def delete_coin(db: Session, coin: Coin) -> None:
    db.execute(delete(Candle).where(Candle.coin_id == coin.id))
    db.execute(delete(IndicatorCache).where(IndicatorCache.coin_id == coin.id))
    db.execute(delete(Signal).where(Signal.coin_id == coin.id))
    delete_coin_metrics_row(db, coin.id)
    coin.enabled = False
    coin.deleted_at = utc_now()
    coin.history_backfill_completed_at = None
    coin.last_history_sync_at = None
    coin.next_history_sync_at = None
    coin.last_history_sync_error = None
    db.commit()
