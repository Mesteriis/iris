from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Sequence

from sqlalchemy import Select, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from src.apps.market_data.models import Candle
from src.apps.market_data.models import Coin
from src.apps.market_data.domain import ensure_utc, normalize_interval
from src.apps.market_data.sources.base import MarketBar
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value

BASE_TIMEFRAME_MINUTES = 15
TIMEFRAME_INTERVALS: dict[int, str] = {
    15: "15m",
    60: "1h",
    240: "4h",
    1440: "1d",
}
INTERVAL_TO_TIMEFRAME: dict[str, int] = {value: key for key, value in TIMEFRAME_INTERVALS.items()}
AGGREGATE_VIEW_BY_TIMEFRAME: dict[int, str] = {
    60: "candles_1h",
    240: "candles_4h",
    1440: "candles_1d",
}
UPSERT_BATCH_SIZE = 2000


def _aggregate_fallback_log(event: str, /, **fields: object) -> None:
    PERSISTENCE_LOGGER.log(
        logging.WARNING,
        event,
        extra={
            "persistence": {
                "event": event,
                "component_type": "repository",
                "domain": "market_data",
                "component": "timescale_aggregate_adapter",
                **{key: sanitize_log_value(value) for key, value in fields.items()},
            }
        },
    )


def _should_fallback_aggregate_error(error: SQLAlchemyError) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "refresh_continuous_aggregate",
            "materialized view",
            "has not been populated",
            "does not exist",
            "undefinedfunction",
            "undefinedtable",
            "candles_1h",
            "candles_4h",
            "candles_1d",
        )
    )


def _execute_aggregate_all(db: Session, statement, params: dict[str, object]) -> list[object]:
    if isinstance(db, Session):
        bind = db.get_bind()
        with bind.connect() as connection:
            return list(connection.execute(statement, params).all())
    return list(db.execute(statement, params).all())


def _execute_aggregate_first(db: Session, statement, params: dict[str, object]) -> object | None:
    if isinstance(db, Session):
        bind = db.get_bind()
        with bind.connect() as connection:
            return connection.execute(statement, params).first()
    return db.execute(statement, params).first()


@dataclass(slots=True, frozen=True)
class CandlePoint:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None


def timeframe_bucket_interval(timeframe: int) -> str:
    if timeframe == 1440:
        return "1 day"
    hours = timeframe // 60
    return f"{hours} hour" if hours == 1 else f"{hours} hours"


def timeframe_delta(timeframe: int) -> timedelta:
    minutes = int(timeframe)
    return timedelta(minutes=minutes)


def interval_to_timeframe(interval: str) -> int:
    normalized = normalize_interval(interval)
    return INTERVAL_TO_TIMEFRAME[normalized]


def align_timeframe_timestamp(value: datetime, timeframe: int) -> datetime:
    current = ensure_utc(value)
    seconds = int(timeframe_delta(timeframe).total_seconds())
    aligned = int(current.timestamp()) // seconds * seconds
    return datetime.fromtimestamp(aligned, tz=timezone.utc)


def candle_close_timestamp(value: datetime, timeframe: int) -> datetime:
    return ensure_utc(value) + timeframe_delta(timeframe)


def _rows_to_candle_points(rows: Sequence[object], *, timestamp_field: str = "timestamp") -> list[CandlePoint]:
    return [
        CandlePoint(
            timestamp=ensure_utc(getattr(row, timestamp_field)),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume) if row.volume is not None else None,
        )
        for row in rows
    ]


def _resample_candle_points(points: Sequence[CandlePoint], *, target_timeframe: int) -> list[CandlePoint]:
    grouped: dict[datetime, dict[str, float | datetime | None]] = {}
    for point in sorted(points, key=lambda value: value.timestamp):
        bucket = align_timeframe_timestamp(point.timestamp, target_timeframe)
        current = grouped.get(bucket)
        if current is None:
            grouped[bucket] = {
                "timestamp": bucket,
                "open": point.open,
                "high": point.high,
                "low": point.low,
                "close": point.close,
                "volume": point.volume,
            }
            continue
        current["high"] = max(float(current["high"]), point.high)
        current["low"] = min(float(current["low"]), point.low)
        current["close"] = point.close
        if point.volume is not None:
            current["volume"] = (
                point.volume if current["volume"] is None else float(current["volume"]) + point.volume
            )
    return [
        CandlePoint(
            timestamp=ensure_utc(bucket),
            open=float(values["open"]),
            high=float(values["high"]),
            low=float(values["low"]),
            close=float(values["close"]),
            volume=float(values["volume"]) if values["volume"] is not None else None,
        )
        for bucket, values in grouped.items()
    ]


def _fetch_direct_candle_points(db: Session, coin_id: int, timeframe: int, limit: int | None) -> list[CandlePoint]:
    stmt = (
        select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
        .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
        .order_by(Candle.timestamp.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = list(reversed(db.execute(stmt).all()))
    return _rows_to_candle_points(rows)


def _fetch_direct_candle_points_between(
    db: Session,
    coin_id: int,
    timeframe: int,
    start: datetime,
    end: datetime,
) -> list[CandlePoint]:
    rows = db.execute(
        select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
        .where(
            Candle.coin_id == coin_id,
            Candle.timeframe == timeframe,
            Candle.timestamp >= ensure_utc(start),
            Candle.timestamp <= ensure_utc(end),
        )
        .order_by(Candle.timestamp.asc())
    ).all()
    return _rows_to_candle_points(rows)


def _fetch_view_candle_points(db: Session, coin_id: int, timeframe: int, limit: int | None) -> list[CandlePoint]:
    view_name = AGGREGATE_VIEW_BY_TIMEFRAME[timeframe]
    limit_sql = "LIMIT :limit" if limit is not None else ""
    query = text(
        f"""
        SELECT bucket, open, high, low, close, volume
        FROM (
            SELECT bucket, open, high, low, close, volume
            FROM {view_name}
            WHERE coin_id = :coin_id
            ORDER BY bucket DESC
            {limit_sql}
        ) AS rows
        ORDER BY bucket ASC
        """
    )
    params = {"coin_id": coin_id}
    if limit is not None:
        params["limit"] = limit
    try:
        rows = _execute_aggregate_all(db, query, params)
    except SQLAlchemyError as error:
        if not _should_fallback_aggregate_error(error):
            raise
        _aggregate_fallback_log(
            "aggregate.view_read.fallback",
            timeframe=timeframe,
            coin_id=coin_id,
            limit=limit,
            error=str(error),
        )
        return []
    return _rows_to_candle_points(rows, timestamp_field="bucket")


def _fetch_view_candle_points_between(
    db: Session,
    coin_id: int,
    timeframe: int,
    start: datetime,
    end: datetime,
) -> list[CandlePoint]:
    view_name = AGGREGATE_VIEW_BY_TIMEFRAME[timeframe]
    try:
        rows = _execute_aggregate_all(
            db,
            text(
                f"""
                SELECT bucket, open, high, low, close, volume
                FROM {view_name}
                WHERE coin_id = :coin_id
                  AND bucket >= :start
                  AND bucket <= :end
                ORDER BY bucket ASC
                """
            ),
            {"coin_id": coin_id, "start": ensure_utc(start), "end": ensure_utc(end)},
        )
    except SQLAlchemyError as error:
        if not _should_fallback_aggregate_error(error):
            raise
        _aggregate_fallback_log(
            "aggregate.view_range_read.fallback",
            timeframe=timeframe,
            coin_id=coin_id,
            start=ensure_utc(start).isoformat(),
            end=ensure_utc(end).isoformat(),
            error=str(error),
        )
        return []
    return _rows_to_candle_points(rows, timestamp_field="bucket")


def get_lowest_available_candle_timeframe(
    db: Session,
    coin_id: int,
    *,
    max_timeframe: int | None = None,
) -> int | None:
    stmt = select(func.min(Candle.timeframe)).where(Candle.coin_id == coin_id)
    if max_timeframe is not None:
        stmt = stmt.where(Candle.timeframe <= max_timeframe)
    value = db.scalar(stmt)
    return int(value) if value is not None else None


def _fetch_resampled_candle_points(
    db: Session,
    coin_id: int,
    source_timeframe: int,
    target_timeframe: int,
    limit: int | None,
) -> list[CandlePoint]:
    limit_sql = "LIMIT :limit" if limit is not None else ""
    query = text(
        f"""
        SELECT bucket, open, high, low, close, volume
        FROM (
            SELECT
                time_bucket(CAST(:bucket_interval AS INTERVAL), timestamp) AS bucket,
                first(open, timestamp) AS open,
                max(high) AS high,
                min(low) AS low,
                last(close, timestamp) AS close,
                sum(volume) AS volume
            FROM candles
            WHERE coin_id = :coin_id
              AND timeframe = :source_timeframe
            GROUP BY bucket
            ORDER BY bucket DESC
            {limit_sql}
        ) AS rows
        ORDER BY bucket ASC
        """
    )
    params: dict[str, object] = {
        "coin_id": coin_id,
        "source_timeframe": source_timeframe,
        "bucket_interval": timeframe_bucket_interval(target_timeframe),
    }
    if limit is not None:
        params["limit"] = limit
    try:
        rows = _execute_aggregate_all(db, query, params)
    except SQLAlchemyError as error:
        if not _should_fallback_aggregate_error(error):
            raise
        _aggregate_fallback_log(
            "aggregate.resample_read.fallback",
            coin_id=coin_id,
            source_timeframe=source_timeframe,
            target_timeframe=target_timeframe,
            limit=limit,
            error=str(error),
        )
        source_points = _fetch_direct_candle_points(db, coin_id, source_timeframe, None)
        resampled = _resample_candle_points(source_points, target_timeframe=target_timeframe)
        return resampled[-limit:] if limit is not None else resampled
    return _rows_to_candle_points(rows, timestamp_field="bucket")


def _fetch_resampled_candle_points_between(
    db: Session,
    coin_id: int,
    source_timeframe: int,
    target_timeframe: int,
    start: datetime,
    end: datetime,
) -> list[CandlePoint]:
    params = {
        "coin_id": coin_id,
        "source_timeframe": source_timeframe,
        "bucket_interval": timeframe_bucket_interval(target_timeframe),
        "start": ensure_utc(start),
        "end": ensure_utc(end),
    }
    try:
        rows = _execute_aggregate_all(
            db,
            text(
                f"""
                SELECT
                    time_bucket(CAST(:bucket_interval AS INTERVAL), timestamp) AS bucket,
                    first(open, timestamp) AS open,
                    max(high) AS high,
                    min(low) AS low,
                    last(close, timestamp) AS close,
                    sum(volume) AS volume
                FROM candles
                WHERE coin_id = :coin_id
                  AND timeframe = :source_timeframe
                  AND timestamp >= :start
                  AND timestamp <= :end
                GROUP BY bucket
                ORDER BY bucket ASC
                """
            ),
            params,
        )
    except SQLAlchemyError as error:
        if not _should_fallback_aggregate_error(error):
            raise
        _aggregate_fallback_log(
            "aggregate.resample_range_read.fallback",
            coin_id=coin_id,
            source_timeframe=source_timeframe,
            target_timeframe=target_timeframe,
            start=ensure_utc(start).isoformat(),
            end=ensure_utc(end).isoformat(),
            error=str(error),
        )
        source_points = _fetch_direct_candle_points_between(db, coin_id, source_timeframe, start, end)
        return _resample_candle_points(source_points, target_timeframe=target_timeframe)
    return _rows_to_candle_points(rows, timestamp_field="bucket")


def get_latest_candle_timestamp(db: Session, coin_id: int, timeframe: int = BASE_TIMEFRAME_MINUTES) -> datetime | None:
    stmt = select(func.max(Candle.timestamp)).where(
        Candle.coin_id == coin_id,
        Candle.timeframe == timeframe,
    )
    latest_direct = db.scalar(stmt)
    if latest_direct is not None:
        return ensure_utc(latest_direct)

    if timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
        view_name = AGGREGATE_VIEW_BY_TIMEFRAME[timeframe]
        try:
            row = _execute_aggregate_first(
                db,
                text(f"SELECT MAX(bucket) AS bucket FROM {view_name} WHERE coin_id = :coin_id"),
                {"coin_id": coin_id},
            )
        except SQLAlchemyError as error:
            if not _should_fallback_aggregate_error(error):
                raise
            _aggregate_fallback_log(
                "aggregate.latest_timestamp.fallback",
                timeframe=timeframe,
                coin_id=coin_id,
                error=str(error),
            )
            row = None
        if row is not None and row.bucket is not None:
            return ensure_utc(row.bucket)

        source_timeframe = get_lowest_available_candle_timeframe(db, coin_id, max_timeframe=timeframe)
        if source_timeframe is not None and source_timeframe < timeframe and timeframe % source_timeframe == 0:
            points = _fetch_resampled_candle_points(db, coin_id, source_timeframe, timeframe, 1)
            if points:
                return ensure_utc(points[-1].timestamp)

    return None


def upsert_base_candles(db: Session, coin: Coin, interval: str, bars: Sequence[MarketBar]) -> datetime | None:
    timeframe = interval_to_timeframe(interval)
    if not bars:
        return None

    latest_existing = get_latest_candle_timestamp(db, coin.id, timeframe)
    rows = [
        {
            "coin_id": coin.id,
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
    for offset in range(0, len(rows), UPSERT_BATCH_SIZE):
        chunk = rows[offset : offset + UPSERT_BATCH_SIZE]
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

    earliest_incoming = min(ensure_utc(bar.timestamp) for bar in bars)
    latest_incoming = max(ensure_utc(bar.timestamp) for bar in bars)
    if timeframe == BASE_TIMEFRAME_MINUTES:
        for aggregate_timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
            refresh_continuous_aggregate_range(db, aggregate_timeframe, earliest_incoming, latest_incoming)
    if latest_existing is None or latest_incoming > latest_existing:
        return latest_incoming
    return None


def fetch_candle_points(db: Session, coin_id: int, timeframe: int, limit: int) -> list[CandlePoint]:
    if limit <= 0:
        return []

    direct_points = _fetch_direct_candle_points(db, coin_id, timeframe, limit)
    if direct_points:
        return direct_points

    if timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
        view_points = _fetch_view_candle_points(db, coin_id, timeframe, limit)
        if view_points:
            return view_points

        source_timeframe = get_lowest_available_candle_timeframe(db, coin_id, max_timeframe=timeframe)
        if source_timeframe is not None and source_timeframe < timeframe and timeframe % source_timeframe == 0:
            return _fetch_resampled_candle_points(db, coin_id, source_timeframe, timeframe, limit)

    return []


def fetch_candle_points_between(
    db: Session,
    coin_id: int,
    timeframe: int,
    start: datetime,
    end: datetime,
) -> list[CandlePoint]:
    direct_points = _fetch_direct_candle_points_between(db, coin_id, timeframe, start, end)
    if direct_points:
        return direct_points

    if timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
        view_points = _fetch_view_candle_points_between(db, coin_id, timeframe, start, end)
        if view_points:
            return view_points

        source_timeframe = get_lowest_available_candle_timeframe(db, coin_id, max_timeframe=timeframe)
        if source_timeframe is not None and source_timeframe < timeframe and timeframe % source_timeframe == 0:
            return _fetch_resampled_candle_points_between(db, coin_id, source_timeframe, timeframe, start, end)

    return []


def get_base_candle_bounds(db: Session, coin_id: int) -> tuple[datetime | None, datetime | None]:
    row = db.execute(
        select(
            func.min(Candle.timestamp).label("first_timestamp"),
            func.max(Candle.timestamp).label("last_timestamp"),
        ).where(
            Candle.coin_id == coin_id,
            Candle.timeframe == BASE_TIMEFRAME_MINUTES,
        )
    ).one()
    first_timestamp = ensure_utc(row.first_timestamp) if row.first_timestamp is not None else None
    last_timestamp = ensure_utc(row.last_timestamp) if row.last_timestamp is not None else None
    return first_timestamp, last_timestamp


def aggregate_has_rows(db: Session, coin_id: int, timeframe: int) -> bool:
    if timeframe not in AGGREGATE_VIEW_BY_TIMEFRAME:
        return False

    view_name = AGGREGATE_VIEW_BY_TIMEFRAME[timeframe]
    try:
        row = _execute_aggregate_first(
            db,
            text(f"SELECT 1 FROM {view_name} WHERE coin_id = :coin_id LIMIT 1"),
            {"coin_id": coin_id},
        )
    except SQLAlchemyError as error:
        if not _should_fallback_aggregate_error(error):
            raise
        _aggregate_fallback_log(
            "aggregate.has_rows.fallback",
            timeframe=timeframe,
            coin_id=coin_id,
            error=str(error),
        )
        return False
    return row is not None


def refresh_continuous_aggregate_range(
    db: Session,
    timeframe: int,
    window_start: datetime,
    window_end: datetime,
) -> None:
    if timeframe not in AGGREGATE_VIEW_BY_TIMEFRAME:
        return

    aligned_start = align_timeframe_timestamp(window_start, timeframe)
    aligned_end = align_timeframe_timestamp(window_end, timeframe) + timeframe_delta(timeframe)
    bind = db.get_bind()
    with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        try:
            connection.execute(
                text("CALL refresh_continuous_aggregate(:view_name, :window_start, :window_end)"),
                {
                    "view_name": AGGREGATE_VIEW_BY_TIMEFRAME[timeframe],
                    "window_start": aligned_start,
                    "window_end": aligned_end,
                },
            )
        except SQLAlchemyError as error:
            if not _should_fallback_aggregate_error(error):
                raise
            _aggregate_fallback_log(
                "aggregate.refresh.skipped",
                timeframe=timeframe,
                view_name=AGGREGATE_VIEW_BY_TIMEFRAME[timeframe],
                window_start=aligned_start.isoformat(),
                window_end=aligned_end.isoformat(),
                error=str(error),
            )


def refresh_continuous_aggregate_window(db: Session, timeframe: int, candle_timestamp: datetime) -> None:
    if timeframe not in AGGREGATE_VIEW_BY_TIMEFRAME:
        return

    bucket_start = align_timeframe_timestamp(candle_timestamp, timeframe)
    refresh_continuous_aggregate_range(db, timeframe, bucket_start, bucket_start)
