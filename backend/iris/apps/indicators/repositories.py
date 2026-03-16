from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from sqlalchemy import Interval, column, delete, func, select, table
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from iris.apps.cross_market.models import SectorMetric
from iris.apps.indicators.analytics import INDICATOR_VERSION, SIGNAL_TYPES, TimeframeSnapshot
from iris.apps.indicators.models import CoinMetrics, FeatureSnapshot, IndicatorCache
from iris.apps.market_data.candles import (
    AGGREGATE_VIEW_BY_TIMEFRAME,
    BASE_TIMEFRAME_MINUTES,
    CandlePoint,
    align_timeframe_timestamp,
    timeframe_bucket_interval,
    timeframe_delta,
)
from iris.apps.market_data.domain import ensure_utc, utc_now
from iris.apps.market_data.models import Candle, Coin
from iris.apps.patterns.models import MarketCycle, PatternFeature
from iris.apps.signals.models import Signal
from iris.core.db.persistence import AsyncRepository


class _CandleRowLike(Protocol):
    open: object
    high: object
    low: object
    close: object
    volume: object | None


@dataclass(slots=True)
class _ResampledBucket:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None


def _float_value(value: object) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    return float(cast(Any, value))


def _rows_to_candle_points(rows: Sequence[object], *, timestamp_field: str = "timestamp") -> list[CandlePoint]:
    return [
        CandlePoint(
            timestamp=ensure_utc(cast(datetime, getattr(row, timestamp_field))),
            open=_float_value(cast(_CandleRowLike, row).open),
            high=_float_value(cast(_CandleRowLike, row).high),
            low=_float_value(cast(_CandleRowLike, row).low),
            close=_float_value(cast(_CandleRowLike, row).close),
            volume=_float_value(cast(_CandleRowLike, row).volume)
            if cast(_CandleRowLike, row).volume is not None
            else None,
        )
        for row in rows
    ]


def _resample_candle_points(points: Sequence[CandlePoint], *, target_timeframe: int) -> list[CandlePoint]:
    grouped: dict[datetime, _ResampledBucket] = {}
    for point in sorted(points, key=lambda value: value.timestamp):
        bucket = align_timeframe_timestamp(point.timestamp, target_timeframe)
        current = grouped.get(bucket)
        if current is None:
            grouped[bucket] = _ResampledBucket(
                timestamp=bucket,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=point.volume,
            )
            continue
        current.high = max(current.high, point.high)
        current.low = min(current.low, point.low)
        current.close = point.close
        if point.volume is not None:
            current.volume = point.volume if current.volume is None else current.volume + point.volume
    return [
        CandlePoint(
            timestamp=ensure_utc(values.timestamp),
            open=values.open,
            high=values.high,
            low=values.low,
            close=values.close,
            volume=values.volume,
        )
        for values in grouped.values()
    ]


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


def _aggregate_view_table(view_name: str) -> Any:
    return table(
        view_name,
        column("coin_id"),
        column("bucket"),
        column("open"),
        column("high"),
        column("low"),
        column("close"),
        column("volume"),
    )


@dataclass(slots=True, frozen=True)
class FeatureSnapshotPayload:
    coin_id: int
    timeframe: int
    timestamp: datetime
    price_current: float | None
    rsi_14: float | None
    macd: float | None
    trend_score: int | None
    volatility: float | None
    sector_strength: float | None
    market_regime: str | None
    cycle_phase: str | None
    pattern_density: int
    cluster_score: float


class IndicatorCoinRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", repository_name="IndicatorCoinRepository")

    async def get_by_id(self, coin_id: int) -> Coin | None:
        self._log_debug("repo.get_indicator_coin_by_id", mode="read", coin_id=coin_id)
        coin = await self.session.get(Coin, int(coin_id))
        self._log_debug("repo.get_indicator_coin_by_id.result", mode="read", found=coin is not None)
        return coin

    async def list_identity_map(self, coin_ids: Sequence[int]) -> dict[int, tuple[str, str, str | None]]:
        normalized_ids = sorted({int(value) for value in coin_ids})
        self._log_debug("repo.list_indicator_coin_identity_map", mode="read", count=len(normalized_ids))
        if not normalized_ids:
            return {}
        rows = (
            await self.session.execute(
                select(Coin.id, Coin.symbol, Coin.name, Coin.sector_code).where(Coin.id.in_(normalized_ids))
            )
        ).all()
        items = {
            int(row.id): (
                str(row.symbol),
                str(row.name),
                str(row.sector_code) if row.sector_code is not None else None,
            )
            for row in rows
        }
        self._log_debug("repo.list_indicator_coin_identity_map.result", mode="read", count=len(items))
        return items


class IndicatorCandleRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", repository_name="IndicatorCandleRepository")

    async def _execute_aggregate_all(self, statement: Any, params: dict[str, object]) -> list[Any]:
        bind = self.session.bind
        if isinstance(bind, AsyncEngine):
            async with bind.connect() as connection:
                return list((await connection.execute(statement, params)).all())
        return list((await self.session.execute(statement, params)).all())

    async def _execute_aggregate_first(self, statement: Any, params: dict[str, object]) -> Any | None:
        bind = self.session.bind
        if isinstance(bind, AsyncEngine):
            async with bind.connect() as connection:
                return (await connection.execute(statement, params)).first()
        return (await self.session.execute(statement, params)).first()

    async def has_direct_candles(self, *, coin_id: int, timeframe: int) -> bool:
        self._log_debug(
            "repo.has_indicator_direct_candles",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        value = (
            await self.session.execute(
                select(Candle.coin_id).where(Candle.coin_id == coin_id, Candle.timeframe == timeframe).limit(1)
            )
        ).scalar_one_or_none()
        found = value is not None
        self._log_debug(
            "repo.has_indicator_direct_candles.result",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            found=found,
        )
        return found

    async def fetch_points(self, *, coin_id: int, timeframe: int, limit: int) -> list[CandlePoint]:
        self._log_debug(
            "repo.fetch_indicator_candle_points",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            limit=limit,
        )
        if limit <= 0:
            return []

        direct_points = await self._fetch_direct_points(coin_id=coin_id, timeframe=timeframe, limit=limit)
        if direct_points:
            self._log_debug(
                "repo.fetch_indicator_candle_points.result",
                mode="read",
                strategy="direct",
                count=len(direct_points),
            )
            return direct_points

        if timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
            view_points = await self._fetch_view_points(coin_id=coin_id, timeframe=timeframe, limit=limit)
            if view_points:
                self._log_debug(
                    "repo.fetch_indicator_candle_points.result",
                    mode="read",
                    strategy="aggregate_view",
                    count=len(view_points),
                    raw_sql_exception=True,
                )
                return view_points

            source_timeframe = await self.get_lowest_available_timeframe(coin_id=coin_id, max_timeframe=timeframe)
            if source_timeframe is not None and source_timeframe < timeframe and timeframe % source_timeframe == 0:
                points = await self._fetch_resampled_points(
                    coin_id=coin_id,
                    source_timeframe=source_timeframe,
                    target_timeframe=timeframe,
                    limit=limit,
                )
                self._log_debug(
                    "repo.fetch_indicator_candle_points.result",
                    mode="read",
                    strategy="resampled",
                    count=len(points),
                    raw_sql_exception=True,
                )
                return points

        self._log_debug("repo.fetch_indicator_candle_points.result", mode="read", strategy="none", count=0)
        return []

    async def get_base_bounds(self, *, coin_id: int) -> tuple[datetime | None, datetime | None]:
        self._log_debug("repo.get_indicator_base_candle_bounds", mode="read", coin_id=coin_id)
        row = (
            await self.session.execute(
                select(
                    func.min(Candle.timestamp).label("first_timestamp"),
                    func.max(Candle.timestamp).label("last_timestamp"),
                ).where(
                    Candle.coin_id == coin_id,
                    Candle.timeframe == BASE_TIMEFRAME_MINUTES,
                )
            )
        ).one()
        first_timestamp = ensure_utc(row.first_timestamp) if row.first_timestamp is not None else None
        last_timestamp = ensure_utc(row.last_timestamp) if row.last_timestamp is not None else None
        self._log_debug(
            "repo.get_indicator_base_candle_bounds.result",
            mode="read",
            coin_id=coin_id,
            has_bounds=first_timestamp is not None and last_timestamp is not None,
        )
        return first_timestamp, last_timestamp

    async def aggregate_has_rows(self, *, coin_id: int, timeframe: int) -> bool:
        self._log_debug(
            "repo.indicator_aggregate_has_rows",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        if timeframe not in AGGREGATE_VIEW_BY_TIMEFRAME:
            return False
        aggregate_view = _aggregate_view_table(AGGREGATE_VIEW_BY_TIMEFRAME[timeframe])
        try:
            row = await self._execute_aggregate_first(
                select(aggregate_view.c.coin_id).where(aggregate_view.c.coin_id == coin_id).limit(1),
                {},
            )
        except SQLAlchemyError as error:
            if not _should_fallback_aggregate_error(error):
                raise
            self._log_warning(
                "repo.indicator_aggregate_has_rows.fallback",
                mode="read",
                coin_id=coin_id,
                timeframe=timeframe,
                error=str(error),
                raw_sql_exception=True,
            )
            return False
        found = row is not None
        self._log_debug(
            "repo.indicator_aggregate_has_rows.result",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            found=found,
            raw_sql_exception=True,
        )
        return found

    async def get_lowest_available_timeframe(
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

    async def _fetch_direct_points(self, *, coin_id: int, timeframe: int, limit: int | None) -> list[CandlePoint]:
        stmt = (
            select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
            .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list(reversed((await self.session.execute(stmt)).all()))
        return _rows_to_candle_points(rows)

    async def _fetch_view_points(self, *, coin_id: int, timeframe: int, limit: int | None) -> list[CandlePoint]:
        view_name = AGGREGATE_VIEW_BY_TIMEFRAME[timeframe]
        aggregate_view = _aggregate_view_table(view_name)
        base_query = (
            select(
                aggregate_view.c.bucket,
                aggregate_view.c.open,
                aggregate_view.c.high,
                aggregate_view.c.low,
                aggregate_view.c.close,
                aggregate_view.c.volume,
            )
            .where(aggregate_view.c.coin_id == coin_id)
            .order_by(aggregate_view.c.bucket.desc())
        )
        if limit is not None:
            base_query = base_query.limit(limit)
        ordered_rows = base_query.subquery()
        try:
            rows = await self._execute_aggregate_all(
                select(
                    ordered_rows.c.bucket,
                    ordered_rows.c.open,
                    ordered_rows.c.high,
                    ordered_rows.c.low,
                    ordered_rows.c.close,
                    ordered_rows.c.volume,
                ).order_by(ordered_rows.c.bucket.asc()),
                {},
            )
        except SQLAlchemyError as error:
            if not _should_fallback_aggregate_error(error):
                raise
            self._log_warning(
                "repo.fetch_indicator_candle_points.aggregate_fallback",
                mode="read",
                coin_id=coin_id,
                timeframe=timeframe,
                limit=limit,
                error=str(error),
                raw_sql_exception=True,
            )
            return []
        return _rows_to_candle_points(rows, timestamp_field="bucket")

    async def _fetch_resampled_points(
        self,
        *,
        coin_id: int,
        source_timeframe: int,
        target_timeframe: int,
        limit: int | None,
    ) -> list[CandlePoint]:
        bucket = func.time_bucket(sql_cast(timeframe_bucket_interval(target_timeframe), Interval()), Candle.timestamp)
        base_query = (
            select(
                bucket.label("bucket"),
                func.first(Candle.open, Candle.timestamp).label("open"),
                func.max(Candle.high).label("high"),
                func.min(Candle.low).label("low"),
                func.last(Candle.close, Candle.timestamp).label("close"),
                func.sum(Candle.volume).label("volume"),
            )
            .where(
                Candle.coin_id == coin_id,
                Candle.timeframe == source_timeframe,
            )
            .group_by(bucket)
            .order_by(bucket.desc())
        )
        if limit is not None:
            base_query = base_query.limit(limit)
        ordered_rows = base_query.subquery()
        try:
            rows = await self._execute_aggregate_all(
                select(
                    ordered_rows.c.bucket,
                    ordered_rows.c.open,
                    ordered_rows.c.high,
                    ordered_rows.c.low,
                    ordered_rows.c.close,
                    ordered_rows.c.volume,
                ).order_by(ordered_rows.c.bucket.asc()),
                {},
            )
            return _rows_to_candle_points(rows, timestamp_field="bucket")
        except SQLAlchemyError as error:
            if not _should_fallback_aggregate_error(error):
                raise
            self._log_warning(
                "repo.fetch_indicator_candle_points.resample_fallback",
                mode="read",
                coin_id=coin_id,
                source_timeframe=source_timeframe,
                target_timeframe=target_timeframe,
                limit=limit,
                error=str(error),
                raw_sql_exception=True,
            )
            source_points = await self._fetch_direct_points(coin_id=coin_id, timeframe=source_timeframe, limit=None)
            resampled = _resample_candle_points(source_points, target_timeframe=target_timeframe)
            return resampled[-limit:] if limit is not None else resampled


class IndicatorMetricsRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", repository_name="IndicatorMetricsRepository")

    async def ensure_row(self, coin_id: int) -> None:
        self._log_info("repo.ensure_indicator_metrics_row", mode="write", coin_id=coin_id)
        stmt = insert(CoinMetrics).values(
            {"coin_id": coin_id, "updated_at": utc_now(), "indicator_version": INDICATOR_VERSION}
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["coin_id"])
        await self.session.execute(stmt)
        await self.session.flush()

    async def delete_by_coin_id(self, coin_id: int) -> int:
        self._log_info("repo.delete_indicator_metrics_row", mode="write", coin_id=coin_id, bulk=True)
        result = await self.session.execute(delete(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
        await self.session.flush()
        return int(cast(Any, result).rowcount or 0)

    async def get_by_coin_id(self, coin_id: int) -> CoinMetrics | None:
        self._log_debug("repo.get_indicator_metrics_by_coin_id", mode="read", coin_id=coin_id)
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id).limit(1))
        self._log_debug("repo.get_indicator_metrics_by_coin_id.result", mode="read", found=metrics is not None)
        return metrics

    async def get_market_cap(self, coin_id: int) -> float | None:
        value = (
            await self.session.execute(select(CoinMetrics.market_cap).where(CoinMetrics.coin_id == coin_id).limit(1))
        ).scalar_one_or_none()
        return float(value) if value is not None else None

    async def upsert(self, payload: Mapping[str, Any]) -> None:
        self._log_info("repo.upsert_indicator_metrics", mode="write", coin_id=int(payload["coin_id"]))
        stmt = insert(CoinMetrics).values(dict(payload))
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id"],
            set_={column: getattr(stmt.excluded, column) for column in payload if column != "coin_id"},
        )
        await self.session.execute(stmt)
        await self.session.flush()


class IndicatorCacheRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", repository_name="IndicatorCacheRepository")

    async def upsert_snapshots(
        self,
        *,
        coin_id: int,
        snapshots: Sequence[TimeframeSnapshot],
        volume_24h: float | None,
        volume_change_24h: float | None,
    ) -> None:
        self._log_info(
            "repo.upsert_indicator_cache_rows",
            mode="write",
            coin_id=coin_id,
            bulk=True,
            count=len(snapshots),
            strategy="core_upsert",
        )
        rows: list[dict[str, Any]] = []
        for snapshot in snapshots:
            values = {
                "price_current": snapshot.price_current,
                "ema_20": snapshot.ema_20,
                "ema_50": snapshot.ema_50,
                "sma_50": snapshot.sma_50,
                "sma_200": snapshot.sma_200,
                "rsi_14": snapshot.rsi_14,
                "macd": snapshot.macd,
                "macd_signal": snapshot.macd_signal,
                "macd_histogram": snapshot.macd_histogram,
                "atr_14": snapshot.atr_14,
                "bb_upper": snapshot.bb_upper,
                "bb_middle": snapshot.bb_middle,
                "bb_lower": snapshot.bb_lower,
                "bb_width": snapshot.bb_width,
                "adx_14": snapshot.adx_14,
            }
            if snapshot.timeframe == BASE_TIMEFRAME_MINUTES:
                values["volume_24h"] = volume_24h
                values["volume_change_24h"] = volume_change_24h
            for indicator_name, indicator_value in values.items():
                rows.append(
                    {
                        "coin_id": coin_id,
                        "timeframe": snapshot.timeframe,
                        "indicator": indicator_name,
                        "value": indicator_value,
                        "timestamp": snapshot.candle_timestamp,
                        "indicator_version": INDICATOR_VERSION,
                        "feature_source": snapshot.feature_source,
                    }
                )
        if not rows:
            return
        stmt = insert(IndicatorCache).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe", "indicator", "timestamp", "indicator_version"],
            set_={
                "value": stmt.excluded.value,
                "feature_source": stmt.excluded.feature_source,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()


class IndicatorSignalRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", repository_name="IndicatorSignalRepository")

    async def insert_known_signals(
        self,
        *,
        coin_id: int,
        timeframe: int,
        signals: Sequence[Mapping[str, Any]],
    ) -> None:
        rows = [
            {
                "coin_id": coin_id,
                "timeframe": timeframe,
                "signal_type": str(item["signal_type"]),
                "confidence": float(item["confidence"]),
                "candle_timestamp": item["candle_timestamp"],
            }
            for item in signals
            if str(item["signal_type"]) in SIGNAL_TYPES
        ]
        self._log_info(
            "repo.insert_indicator_signals",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            bulk=True,
            count=len(rows),
        )
        if not rows:
            return
        stmt = insert(Signal).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["coin_id", "timeframe", "candle_timestamp", "signal_type"])
        await self.session.execute(stmt)
        await self.session.flush()

    async def list_types_at_timestamp(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object,
    ) -> set[str]:
        self._log_debug(
            "repo.list_indicator_signal_types_at_timestamp",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        rows = await self.session.scalars(
            select(Signal.signal_type).where(
                Signal.coin_id == coin_id,
                Signal.timeframe == timeframe,
                Signal.candle_timestamp == candle_timestamp,
            )
        )
        items = {str(value) for value in rows.all()}
        self._log_debug("repo.list_indicator_signal_types_at_timestamp.result", mode="read", count=len(items))
        return items

    async def list_pattern_signal_rows(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: object,
    ) -> Sequence[object]:
        self._log_debug(
            "repo.list_indicator_pattern_signal_rows",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        rows = (
            await self.session.execute(
                select(Signal.signal_type, Signal.priority_score, Signal.confidence).where(
                    Signal.coin_id == coin_id,
                    Signal.timeframe == timeframe,
                    Signal.candle_timestamp == timestamp,
                    Signal.signal_type.like("pattern_%"),
                )
            )
        ).all()
        self._log_debug("repo.list_indicator_pattern_signal_rows.result", mode="read", count=len(rows))
        return rows


class IndicatorFeatureSnapshotRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", repository_name="IndicatorFeatureSnapshotRepository")

    async def upsert(self, payload: FeatureSnapshotPayload) -> None:
        self._log_info(
            "repo.upsert_indicator_feature_snapshot",
            mode="write",
            coin_id=payload.coin_id,
            timeframe=payload.timeframe,
        )
        stmt = insert(FeatureSnapshot).values(
            {
                "coin_id": payload.coin_id,
                "timeframe": payload.timeframe,
                "timestamp": payload.timestamp,
                "price_current": payload.price_current,
                "rsi_14": payload.rsi_14,
                "macd": payload.macd,
                "trend_score": payload.trend_score,
                "volatility": payload.volatility,
                "sector_strength": payload.sector_strength,
                "market_regime": payload.market_regime,
                "cycle_phase": payload.cycle_phase,
                "pattern_density": payload.pattern_density,
                "cluster_score": payload.cluster_score,
            }
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe", "timestamp"],
            set_={
                "price_current": stmt.excluded.price_current,
                "rsi_14": stmt.excluded.rsi_14,
                "macd": stmt.excluded.macd,
                "trend_score": stmt.excluded.trend_score,
                "volatility": stmt.excluded.volatility,
                "sector_strength": stmt.excluded.sector_strength,
                "market_regime": stmt.excluded.market_regime,
                "cycle_phase": stmt.excluded.cycle_phase,
                "pattern_density": stmt.excluded.pattern_density,
                "cluster_score": stmt.excluded.cluster_score,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()


class IndicatorSectorMetricRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", repository_name="IndicatorSectorMetricRepository")

    async def get_by_key(self, *, sector_id: int, timeframe: int) -> SectorMetric | None:
        return await self.session.get(SectorMetric, (sector_id, timeframe))


class IndicatorMarketCycleRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", repository_name="IndicatorMarketCycleRepository")

    async def get_by_key(self, *, coin_id: int, timeframe: int) -> MarketCycle | None:
        return await self.session.get(MarketCycle, (coin_id, timeframe))


class IndicatorFeatureFlagRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", repository_name="IndicatorFeatureFlagRepository")

    async def is_enabled(self, feature_slug: str) -> bool:
        self._log_debug("repo.get_indicator_feature_flag", mode="read", feature_slug=feature_slug)
        value = (
            await self.session.execute(
                select(PatternFeature.enabled).where(PatternFeature.feature_slug == feature_slug).limit(1)
            )
        ).scalar_one_or_none()
        enabled = bool(value) if value is not None else False
        self._log_debug(
            "repo.get_indicator_feature_flag.result", mode="read", feature_slug=feature_slug, enabled=enabled
        )
        return enabled


__all__ = [
    "FeatureSnapshotPayload",
    "IndicatorCacheRepository",
    "IndicatorCandleRepository",
    "IndicatorCoinRepository",
    "IndicatorFeatureFlagRepository",
    "IndicatorFeatureSnapshotRepository",
    "IndicatorMarketCycleRepository",
    "IndicatorMetricsRepository",
    "IndicatorSectorMetricRepository",
    "IndicatorSignalRepository",
]
