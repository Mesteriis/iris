from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from src.apps.indicators.analytics import (
    INDICATOR_VERSION,
    TimeframeSnapshot,
)
from src.apps.indicators.repositories import IndicatorCandleRepository, IndicatorMetricsRepository
from src.apps.indicators.results import IndicatorMetricsUpdate
from src.apps.market_data.candles import AGGREGATE_VIEW_BY_TIMEFRAME
from src.apps.market_data.models import Coin
from src.apps.market_data.repositories import TimescaleContinuousAggregateRepository
from src.core.db.session import async_engine


class IndicatorAggregateRefresher:
    def __init__(self) -> None:
        self._repo = TimescaleContinuousAggregateRepository(async_engine)

    async def refresh_range(
        self,
        *,
        timeframe: int,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        await self._repo.refresh_range(
            timeframe=timeframe,
            window_start=window_start,
            window_end=window_end,
        )


def regime_for_timeframe(
    *,
    timeframe: int,
    regime_map: dict[int, object],
    fallback: str | None,
) -> tuple[str | None, float | None]:
    regime = regime_map.get(timeframe)
    if regime is None:
        return fallback, None
    return str(regime.regime), float(regime.confidence)


async def refresh_missing_aggregates(
    *,
    coin_id: int,
    event_timestamp: datetime,
    affected_timeframes: list[int],
    base_window_start: datetime | None,
    base_window_end: datetime | None,
    candles: IndicatorCandleRepository,
    aggregates: IndicatorAggregateRefresher,
) -> None:
    if base_window_start is not None and base_window_end is not None:
        for aggregate_timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
            if not await candles.aggregate_has_rows(coin_id=coin_id, timeframe=aggregate_timeframe):
                await aggregates.refresh_range(
                    timeframe=aggregate_timeframe,
                    window_start=base_window_start,
                    window_end=base_window_end,
                )

    for affected_timeframe in affected_timeframes:
        if affected_timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
            await aggregates.refresh_range(
                timeframe=affected_timeframe,
                window_start=event_timestamp,
                window_end=event_timestamp,
            )


async def upsert_indicator_coin_metrics(
    *,
    coin: Coin,
    base_timeframe: int,
    primary: TimeframeSnapshot | None,
    base_snapshot: TimeframeSnapshot | None,
    base_candles: list[object],
    volume_24h: float | None,
    volume_change_24h: float | None,
    volatility: float | None,
    refresh_market_cap: bool,
    market_regime: str | None,
    market_regime_details: dict[str, object] | None,
    metrics: IndicatorMetricsRepository,
    activity_fields: Callable[..., tuple[float | None, str | None, int | None]],
    compute_market_regime: Callable[[TimeframeSnapshot, str, float | None], str],
    compute_price_change: Callable[[list[object], timedelta], float | None],
    compute_trend: Callable[[TimeframeSnapshot], str],
    compute_trend_score: Callable[[TimeframeSnapshot, float | None], int],
    fetch_market_cap: Callable[[str], Awaitable[float | None]],
    now_fn: Callable[[], datetime],
) -> IndicatorMetricsUpdate:
    await metrics.ensure_row(int(coin.id))
    if primary is None:
        return IndicatorMetricsUpdate(
            coin_id=int(coin.id),
            market_regime=market_regime,
            market_regime_details=market_regime_details,
        )

    del base_timeframe

    trend = compute_trend(primary)
    trend_score = compute_trend_score(primary, volume_change_24h)
    existing_market_cap = await metrics.get_market_cap(int(coin.id))
    price_current = base_snapshot.price_current if base_snapshot is not None else primary.price_current
    price_change_1h = compute_price_change(base_candles, timedelta(hours=1))
    price_change_24h = compute_price_change(base_candles, timedelta(hours=24))
    price_change_7d = compute_price_change(base_candles, timedelta(days=7))
    activity_score, activity_bucket, analysis_priority = activity_fields(
        price_change_24h=price_change_24h,
        volatility=volatility,
        volume_change_24h=volume_change_24h,
        price_current=price_current,
    )
    payload = {
        "coin_id": int(coin.id),
        "price_current": price_current,
        "price_change_1h": price_change_1h,
        "price_change_24h": price_change_24h,
        "price_change_7d": price_change_7d,
        "ema_20": primary.ema_20,
        "ema_50": primary.ema_50,
        "sma_50": primary.sma_50,
        "sma_200": primary.sma_200,
        "rsi_14": primary.rsi_14,
        "macd": primary.macd,
        "macd_signal": primary.macd_signal,
        "macd_histogram": primary.macd_histogram,
        "atr_14": primary.atr_14,
        "bb_upper": primary.bb_upper,
        "bb_middle": primary.bb_middle,
        "bb_lower": primary.bb_lower,
        "bb_width": primary.bb_width,
        "adx_14": primary.adx_14,
        "volume_24h": volume_24h,
        "volume_change_24h": volume_change_24h,
        "volatility": volatility,
        "market_cap": await fetch_market_cap(coin.symbol)
        if refresh_market_cap or existing_market_cap is None
        else existing_market_cap,
        "trend": trend,
        "trend_score": trend_score,
        "activity_score": activity_score,
        "activity_bucket": activity_bucket,
        "analysis_priority": analysis_priority,
        "market_regime": market_regime or compute_market_regime(primary, trend, volume_change_24h),
        "market_regime_details": market_regime_details,
        "indicator_version": INDICATOR_VERSION,
        "updated_at": now_fn(),
    }
    await metrics.upsert(payload)
    return IndicatorMetricsUpdate(
        coin_id=int(coin.id),
        activity_score=activity_score,
        activity_bucket=activity_bucket,
        analysis_priority=analysis_priority,
        market_regime=str(payload["market_regime"]) if payload["market_regime"] is not None else None,
        market_regime_details=market_regime_details,
        price_change_24h=price_change_24h,
        price_change_7d=price_change_7d,
        volatility=volatility,
    )


__all__ = [
    "IndicatorAggregateRefresher",
    "refresh_missing_aggregates",
    "regime_for_timeframe",
    "upsert_indicator_coin_metrics",
]
