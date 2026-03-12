from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.apps.indicators.models import CoinMetrics, IndicatorCache
from src.apps.market_data.domain import ensure_utc, normalize_interval
from src.apps.market_data.models import Candle, Coin
from src.apps.market_data.repos import (
    AGGREGATE_VIEW_BY_TIMEFRAME,
    CandlePoint,
    align_timeframe_timestamp,
    interval_to_timeframe,
    timeframe_bucket_interval,
    timeframe_delta,
)
from src.apps.market_data.service_layer import get_base_candle_config
from src.apps.signals.models import Signal
from src.core.db.persistence import PERSISTENCE_LOGGER, AsyncRepository, sanitize_log_value


class CoinRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_data", repository_name="CoinRepository")

    async def add(self, coin: Coin) -> Coin:
        self._log_info("repo.add_market_data_coin", mode="write", symbol=coin.symbol)
        self.session.add(coin)
        await self.session.flush()
        return coin

    async def get_by_id(self, coin_id: int) -> Coin | None:
        self._log_debug("repo.get_market_data_coin_by_id", mode="read", coin_id=coin_id)
        coin = await self.session.get(Coin, int(coin_id))
        self._log_debug("repo.get_market_data_coin_by_id.result", mode="read", found=coin is not None)
        return coin

    async def get_by_symbol(
        self,
        symbol: str,
        *,
        include_deleted: bool = False,
    ) -> Coin | None:
        normalized_symbol = symbol.strip().upper()
        self._log_debug(
            "repo.get_market_data_coin_by_symbol",
            mode="read",
            symbol=normalized_symbol,
            include_deleted=include_deleted,
        )
        stmt = select(Coin).where(Coin.symbol == normalized_symbol)
        if not include_deleted:
            stmt = stmt.where(Coin.deleted_at.is_(None))
        coin = await self.session.scalar(stmt.limit(1))
        self._log_debug("repo.get_market_data_coin_by_symbol.result", mode="read", found=coin is not None)
        return coin

    async def get_for_update_by_symbol(
        self,
        symbol: str,
        *,
        include_deleted: bool = False,
    ) -> Coin | None:
        normalized_symbol = symbol.strip().upper()
        self._log_debug(
            "repo.get_market_data_coin_for_update_by_symbol",
            mode="write",
            symbol=normalized_symbol,
            include_deleted=include_deleted,
            lock=True,
        )
        stmt = select(Coin).where(Coin.symbol == normalized_symbol).with_for_update()
        if not include_deleted:
            stmt = stmt.where(Coin.deleted_at.is_(None))
        coin = await self.session.scalar(stmt.limit(1))
        self._log_debug("repo.get_market_data_coin_for_update_by_symbol.result", mode="write", found=coin is not None)
        return coin

    async def list(
        self,
        *,
        enabled_only: bool = False,
        include_deleted: bool = False,
    ) -> list[Coin]:
        self._log_debug(
            "repo.list_market_data_coins",
            mode="read",
            enabled_only=enabled_only,
            include_deleted=include_deleted,
        )
        stmt = select(Coin)
        if not include_deleted:
            stmt = stmt.where(Coin.deleted_at.is_(None))
        if enabled_only:
            stmt = stmt.where(Coin.enabled.is_(True))
        stmt = stmt.order_by(Coin.sort_order.asc(), Coin.symbol.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        items = list(rows)
        self._log_debug("repo.list_market_data_coins.result", mode="read", count=len(items))
        return items

    async def refresh(self, coin: Coin) -> None:
        await self.session.refresh(coin)


class CandleRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_data", repository_name="CandleRepository")

    @staticmethod
    def _rows_to_candle_points(rows: Sequence[Any], *, timestamp_field: str = "timestamp") -> list[CandlePoint]:
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

    async def get_latest_timestamp(self, *, coin_id: int, timeframe: int) -> datetime | None:
        self._log_debug(
            "repo.get_latest_market_data_candle_timestamp",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        value = (
            await self.session.execute(
                select(Candle.timestamp)
                .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        self._log_debug(
            "repo.get_latest_market_data_candle_timestamp.result",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            found=value is not None,
        )
        return value

    async def list_recent_rows(
        self,
        *,
        coin_id: int,
        timeframe: int,
        limit: int,
    ) -> Sequence[Any]:
        self._log_debug(
            "repo.list_recent_market_data_candles",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            limit=limit,
        )
        rows = (
            await self.session.execute(
                select(Candle.timestamp, Candle.close, Candle.volume)
                .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.desc())
                .limit(max(limit, 1))
            )
        ).all()
        self._log_debug("repo.list_recent_market_data_candles.result", mode="read", count=len(rows))
        return rows

    async def fetch_points(
        self,
        *,
        coin_id: int,
        timeframe: int,
        limit: int,
    ) -> list[CandlePoint]:
        self._log_debug(
            "repo.fetch_market_data_candle_points",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            limit=limit,
        )
        if limit <= 0:
            return []

        direct_rows = (
            await self.session.execute(
                select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
                .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.desc())
                .limit(limit)
            )
        ).all()
        direct_points = self._rows_to_candle_points(list(reversed(direct_rows)))
        if direct_points:
            self._log_debug("repo.fetch_market_data_candle_points.result", mode="read", count=len(direct_points))
            return direct_points

        if timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
            view_name = AGGREGATE_VIEW_BY_TIMEFRAME[timeframe]
            view_rows = (
                await self.session.execute(
                    text(
                        f"""
                        SELECT bucket, open, high, low, close, volume
                        FROM (
                            SELECT bucket, open, high, low, close, volume
                            FROM {view_name}
                            WHERE coin_id = :coin_id
                            ORDER BY bucket DESC
                            LIMIT :limit
                        ) AS rows
                        ORDER BY bucket ASC
                        """
                    ),
                    {"coin_id": coin_id, "limit": limit},
                )
            ).all()
            view_points = self._rows_to_candle_points(view_rows, timestamp_field="bucket")
            if view_points:
                self._log_debug("repo.fetch_market_data_candle_points.result", mode="read", count=len(view_points))
                return view_points

            source_timeframe = await self._get_lowest_available_timeframe(coin_id=coin_id, max_timeframe=timeframe)
            if source_timeframe is not None and source_timeframe < timeframe and timeframe % source_timeframe == 0:
                resampled_rows = (
                    await self.session.execute(
                        text(
                            """
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
                                LIMIT :limit
                            ) AS rows
                            ORDER BY bucket ASC
                            """
                        ),
                        {
                            "coin_id": coin_id,
                            "source_timeframe": source_timeframe,
                            "bucket_interval": timeframe_bucket_interval(timeframe),
                            "limit": limit,
                        },
                    )
                ).all()
                points = self._rows_to_candle_points(resampled_rows, timestamp_field="bucket")
                self._log_debug(
                    "repo.fetch_market_data_candle_points.result",
                    mode="read",
                    count=len(points),
                    fallback="resampled",
                )
                return points

        self._log_debug("repo.fetch_market_data_candle_points.result", mode="read", count=0)
        return []

    async def fetch_points_between(
        self,
        *,
        coin_id: int,
        timeframe: int,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CandlePoint]:
        self._log_debug(
            "repo.fetch_market_data_candle_points_between",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
        )
        direct_rows = (
            await self.session.execute(
                select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
                .where(
                    Candle.coin_id == coin_id,
                    Candle.timeframe == timeframe,
                    Candle.timestamp >= ensure_utc(window_start),
                    Candle.timestamp <= ensure_utc(window_end),
                )
                .order_by(Candle.timestamp.asc())
            )
        ).all()
        direct_points = self._rows_to_candle_points(direct_rows)
        if direct_points:
            self._log_debug(
                "repo.fetch_market_data_candle_points_between.result", mode="read", count=len(direct_points)
            )
            return direct_points

        if timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
            view_name = AGGREGATE_VIEW_BY_TIMEFRAME[timeframe]
            view_rows = (
                await self.session.execute(
                    text(
                        f"""
                        SELECT bucket, open, high, low, close, volume
                        FROM {view_name}
                        WHERE coin_id = :coin_id
                          AND bucket >= :window_start
                          AND bucket <= :window_end
                        ORDER BY bucket ASC
                        """
                    ),
                    {
                        "coin_id": coin_id,
                        "window_start": ensure_utc(window_start),
                        "window_end": ensure_utc(window_end),
                    },
                )
            ).all()
            view_points = self._rows_to_candle_points(view_rows, timestamp_field="bucket")
            if view_points:
                self._log_debug(
                    "repo.fetch_market_data_candle_points_between.result",
                    mode="read",
                    count=len(view_points),
                )
                return view_points

            source_timeframe = await self._get_lowest_available_timeframe(coin_id=coin_id, max_timeframe=timeframe)
            if source_timeframe is not None and source_timeframe < timeframe and timeframe % source_timeframe == 0:
                resampled_rows = (
                    await self.session.execute(
                        text(
                            """
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
                              AND timestamp >= :window_start
                              AND timestamp <= :window_end
                            GROUP BY bucket
                            ORDER BY bucket ASC
                            """
                        ),
                        {
                            "coin_id": coin_id,
                            "source_timeframe": source_timeframe,
                            "bucket_interval": timeframe_bucket_interval(timeframe),
                            "window_start": ensure_utc(window_start),
                            "window_end": ensure_utc(window_end),
                        },
                    )
                ).all()
                points = self._rows_to_candle_points(resampled_rows, timestamp_field="bucket")
                self._log_debug(
                    "repo.fetch_market_data_candle_points_between.result",
                    mode="read",
                    count=len(points),
                    fallback="resampled",
                )
                return points

        self._log_debug("repo.fetch_market_data_candle_points_between.result", mode="read", count=0)
        return []

    async def count_rows_between(
        self,
        *,
        coin_id: int,
        timeframe: int,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        self._log_debug(
            "repo.count_market_data_candles_between",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        value = (
            await self.session.execute(
                select(func.count())
                .select_from(Candle)
                .where(
                    Candle.coin_id == coin_id,
                    Candle.timeframe == timeframe,
                    Candle.timestamp >= window_start,
                    Candle.timestamp <= window_end,
                )
            )
        ).scalar_one()
        count = int(value or 0)
        self._log_debug("repo.count_market_data_candles_between.result", mode="read", count=count)
        return count

    async def delete_by_coin_id(self, coin_id: int) -> int:
        self._log_info("repo.delete_market_data_candles_by_coin", mode="write", coin_id=coin_id, bulk=True)
        result = await self.session.execute(delete(Candle).where(Candle.coin_id == coin_id))
        await self.session.flush()
        return int(result.rowcount or 0)

    async def delete_future_rows(
        self,
        *,
        coin_id: int,
        timeframe: int,
        latest_allowed: datetime,
    ) -> int:
        self._log_info(
            "repo.delete_future_market_data_candles",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            bulk=True,
        )
        result = await self.session.execute(
            delete(Candle).where(
                Candle.coin_id == coin_id,
                Candle.timeframe == timeframe,
                Candle.timestamp > latest_allowed,
            )
        )
        await self.session.flush()
        count = int(result.rowcount or 0)
        self._log_debug("repo.delete_future_market_data_candles.result", mode="write", count=count)
        return count

    async def delete_rows_before(
        self,
        *,
        coin_id: int,
        timeframe: int,
        cutoff: datetime,
    ) -> int:
        self._log_info(
            "repo.delete_market_data_candles_before_cutoff",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            bulk=True,
        )
        result = await self.session.execute(
            delete(Candle).where(
                Candle.coin_id == coin_id,
                Candle.timeframe == timeframe,
                Candle.timestamp < cutoff,
            )
        )
        await self.session.flush()
        count = int(result.rowcount or 0)
        self._log_debug("repo.delete_market_data_candles_before_cutoff.result", mode="write", count=count)
        return count

    async def upsert_row(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: float | None,
    ) -> None:
        self._log_info(
            "repo.upsert_market_data_candle",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=timestamp.isoformat(),
        )
        stmt = insert(Candle).values(
            {
                "coin_id": coin_id,
                "timeframe": timeframe,
                "timestamp": timestamp,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
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
        await self.session.execute(stmt)
        await self.session.flush()

    async def upsert_rows(self, rows: Sequence[dict[str, Any]]) -> None:
        self._log_info("repo.upsert_market_data_candles", mode="write", bulk=True, count=len(rows))
        if not rows:
            return
        stmt = insert(Candle).values(list(rows))
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
        await self.session.execute(stmt)
        await self.session.flush()

    async def list_latest_timestamps_for_pairs(
        self,
        pairs: Sequence[tuple[int, int]],
    ) -> dict[tuple[int, int], datetime]:
        normalized_pairs = sorted({(int(coin_id), int(timeframe)) for coin_id, timeframe in pairs})
        self._log_debug(
            "repo.list_latest_market_data_candle_timestamps_for_pairs",
            mode="read",
            pair_count=len(normalized_pairs),
        )
        if not normalized_pairs:
            return {}
        rows = (
            await self.session.execute(
                select(Candle.coin_id, Candle.timeframe, func.max(Candle.timestamp).label("latest_timestamp"))
                .where(tuple_(Candle.coin_id, Candle.timeframe).in_(normalized_pairs))
                .group_by(Candle.coin_id, Candle.timeframe)
            )
        ).all()
        items = {
            (int(row.coin_id), int(row.timeframe)): row.latest_timestamp
            for row in rows
            if row.latest_timestamp is not None
        }
        self._log_debug(
            "repo.list_latest_market_data_candle_timestamps_for_pairs.result",
            mode="read",
            count=len(items),
        )
        return items

    async def _get_lowest_available_timeframe(
        self,
        *,
        coin_id: int,
        max_timeframe: int | None = None,
    ) -> int | None:
        stmt = select(func.min(Candle.timeframe)).where(Candle.coin_id == coin_id)
        if max_timeframe is not None:
            stmt = stmt.where(Candle.timeframe <= max_timeframe)
        value = (await self.session.execute(stmt)).scalar_one_or_none()
        return int(value) if value is not None else None


class CoinMetricsRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_data", repository_name="CoinMetricsRepository")

    async def ensure_row(self, coin_id: int) -> None:
        self._log_info("repo.ensure_coin_metrics_row", mode="write", coin_id=coin_id)
        stmt = insert(CoinMetrics).values({"coin_id": coin_id, "updated_at": func.now()})
        stmt = stmt.on_conflict_do_nothing(index_elements=["coin_id"])
        await self.session.execute(stmt)
        await self.session.flush()

    async def delete_by_coin_id(self, coin_id: int) -> int:
        self._log_info("repo.delete_coin_metrics_row", mode="write", coin_id=coin_id, bulk=True)
        result = await self.session.execute(delete(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
        await self.session.flush()
        return int(result.rowcount or 0)


class IndicatorCacheRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_data", repository_name="IndicatorCacheRepository")

    async def delete_by_coin_id(self, coin_id: int) -> int:
        self._log_info("repo.delete_indicator_cache_rows", mode="write", coin_id=coin_id, bulk=True)
        result = await self.session.execute(delete(IndicatorCache).where(IndicatorCache.coin_id == coin_id))
        await self.session.flush()
        return int(result.rowcount or 0)


class SignalRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_data", repository_name="SignalRepository")

    async def delete_by_coin_id(self, coin_id: int) -> int:
        self._log_info("repo.delete_signal_rows", mode="write", coin_id=coin_id, bulk=True)
        result = await self.session.execute(delete(Signal).where(Signal.coin_id == coin_id))
        await self.session.flush()
        return int(result.rowcount or 0)


class TimescaleContinuousAggregateRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        payload = {
            "event": event,
            "component_type": "repository",
            "domain": "market_data",
            "component": "TimescaleContinuousAggregateRepository",
            **{key: sanitize_log_value(value) for key, value in fields.items()},
        }
        PERSISTENCE_LOGGER.log(level, event, extra={"persistence": payload})

    def _log_debug(self, event: str, /, **fields: Any) -> None:
        self._log(logging.DEBUG, event, **fields)

    def _log_warning(self, event: str, /, **fields: Any) -> None:
        self._log(logging.WARNING, event, **fields)

    def _log_exception(self, event: str, /, **fields: Any) -> None:
        self._log(logging.ERROR, event, exc_info=True, **fields)

    async def refresh_range(
        self,
        *,
        timeframe: int,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        if timeframe not in AGGREGATE_VIEW_BY_TIMEFRAME:
            self._log_debug(
                "repo.refresh_continuous_aggregate.skipped",
                mode="write",
                timeframe=timeframe,
            )
            return
        aligned_start = align_timeframe_timestamp(window_start, timeframe)
        aligned_end = align_timeframe_timestamp(window_end, timeframe) + timeframe_delta(timeframe)
        self._log_warning(
            "repo.refresh_continuous_aggregate.raw_sql",
            mode="write",
            timeframe=timeframe,
            fallback="timescale_continuous_aggregate_call",
            raw_sql_exception=True,
        )
        try:
            async with self._engine.connect() as connection:
                connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
                await connection.execute(
                    text("CALL refresh_continuous_aggregate(:view_name, :window_start, :window_end)"),
                    {
                        "view_name": AGGREGATE_VIEW_BY_TIMEFRAME[timeframe],
                        "window_start": aligned_start,
                        "window_end": aligned_end,
                    },
                )
        except Exception:
            self._log_exception(
                "repo.refresh_continuous_aggregate.failed",
                mode="write",
                timeframe=timeframe,
            )
            raise


def latest_candle_pair_map(
    *,
    coins: Iterable[Coin],
) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for coin in coins:
        interval = normalize_interval(str(get_base_candle_config(coin)["interval"]))
        pairs.append((int(coin.id), interval_to_timeframe(interval)))
    return pairs


__all__ = [
    "CandleRepository",
    "CoinMetricsRepository",
    "CoinRepository",
    "IndicatorCacheRepository",
    "SignalRepository",
    "TimescaleContinuousAggregateRepository",
    "latest_candle_pair_map",
]
