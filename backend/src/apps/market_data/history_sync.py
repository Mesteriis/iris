from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.market_data import candles as market_data_candles
from src.apps.market_data import domain as market_data_domain
from src.apps.market_data import support as market_data_support
from src.apps.market_data.models import Coin
from src.apps.market_data.repositories import (
    CandleRepository,
    CoinMetricsRepository,
    CoinRepository,
    TimescaleContinuousAggregateRepository,
)
from src.apps.market_data.sources.base import MarketBar
from src.core.db.session import async_engine
from src.core.db.uow import BaseAsyncUnitOfWork


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
            timeframe=market_data_candles.interval_to_timeframe(interval),
            window_start=window_start,
            window_end=latest_available,
        ),
        retention_bars,
    )
    progress_percent = min((loaded_points / total_points) * 100, 100.0)
    return loaded_points, total_points, round(progress_percent, 1)


async def _prune_future_price_history_async(
    uow: BaseAsyncUnitOfWork,
    *,
    coin_id: int,
    interval: str,
    latest_allowed: datetime,
) -> int:
    db = uow.session
    resolved_interval = market_data_domain.normalize_interval(interval)
    timeframe = market_data_candles.interval_to_timeframe(resolved_interval)
    return await CandleRepository(db).delete_future_rows(
        coin_id=coin_id,
        timeframe=timeframe,
        latest_allowed=latest_allowed,
    )


async def _get_latest_history_timestamp_async(
    db: AsyncSession,
    *,
    coin_id: int,
    interval: str,
) -> datetime | None:
    return await CandleRepository(db).get_latest_timestamp(
        coin_id=coin_id,
        timeframe=market_data_candles.interval_to_timeframe(market_data_domain.normalize_interval(interval)),
    )


async def _prune_price_history_async(
    uow: BaseAsyncUnitOfWork,
    *,
    coin_id: int,
    interval: str,
    retention_bars: int,
) -> int:
    db = uow.session
    latest_timestamp = await _get_latest_history_timestamp_async(db, coin_id=coin_id, interval=interval)
    if latest_timestamp is None:
        return 0
    cutoff = market_data_domain.history_window_start(
        latest_timestamp,
        market_data_domain.normalize_interval(interval),
        retention_bars,
    )
    timeframe = market_data_candles.interval_to_timeframe(market_data_domain.normalize_interval(interval))
    return await CandleRepository(db).delete_rows_before(
        coin_id=coin_id,
        timeframe=timeframe,
        cutoff=cutoff,
    )


async def _upsert_base_candles_async(
    uow: BaseAsyncUnitOfWork,
    *,
    coin_id: int,
    interval: str,
    bars: Sequence[MarketBar],
    source: str = "history",
) -> datetime | None:
    db = uow.session
    coin = await CoinRepository(db).get_by_id(int(coin_id))
    if coin is None or not bars:
        return None
    timeframe = market_data_candles.interval_to_timeframe(interval)
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

    created_count = len(rows)
    earliest_incoming = min(market_data_domain.ensure_utc(bar.timestamp) for bar in bars)
    latest_incoming = max(market_data_domain.ensure_utc(bar.timestamp) for bar in bars)
    if timeframe == market_data_candles.BASE_TIMEFRAME_MINUTES:
        for aggregate_timeframe in market_data_candles.AGGREGATE_VIEW_BY_TIMEFRAME:
            def _refresh_aggregate(aggregate_timeframe: int = aggregate_timeframe) -> object:
                return _refresh_continuous_aggregate_range_async(
                    timeframe=aggregate_timeframe,
                    window_start=earliest_incoming,
                    window_end=latest_incoming,
                )

            uow.add_after_commit_action(
                _refresh_aggregate
            )
    if latest_existing is None or latest_incoming > latest_existing:
        def _publish_candle_events() -> None:
            market_data_support.publish_candle_events(
                coin_id=int(coin.id),
                timeframe=timeframe,
                timestamp=latest_incoming,
                created_count=created_count,
                source=source,
            )

        uow.add_after_commit_action(
            _publish_candle_events
        )
        return latest_incoming
    return None


__all__ = [
    "_calculate_backfill_progress_async",
    "_coin_has_base_candles_async",
    "_get_latest_candle_timestamp_async",
    "_get_latest_history_timestamp_async",
    "_prune_future_price_history_async",
    "_prune_price_history_async",
    "_refresh_continuous_aggregate_range_async",
    "_upsert_base_candles_async",
]
