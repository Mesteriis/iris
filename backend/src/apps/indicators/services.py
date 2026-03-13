from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.indicators.analytics import (
    INDICATOR_VERSION,
    PRICE_HISTORY_LOOKBACK_BARS,
    CandleAnalyticsEvent,
    TimeframeSnapshot,
    _activity_fields,
    _calculate_snapshot,
    _coin_base_timeframe,
    _compute_market_regime,
    _compute_price_change,
    _compute_trend,
    _compute_trend_score,
    _compute_volume_metrics,
    _detect_signals,
    _fetch_market_cap,
    _select_primary_snapshot,
    determine_affected_timeframes,
)
from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.indicators.read_models import (
    CoinMetricsReadModel,
    MarketFlowReadModel,
    MarketRadarReadModel,
    SignalSummaryReadModel,
)
from src.apps.indicators.repositories import (
    FeatureSnapshotPayload,
    IndicatorCacheRepository,
    IndicatorCandleRepository,
    IndicatorCoinRepository,
    IndicatorFeatureFlagRepository,
    IndicatorFeatureSnapshotRepository,
    IndicatorMarketCycleRepository,
    IndicatorMetricsRepository,
    IndicatorSectorMetricRepository,
    IndicatorSignalRepository,
)
from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_data.models import Coin
from src.apps.market_data.repos import AGGREGATE_VIEW_BY_TIMEFRAME, BASE_TIMEFRAME_MINUTES, TIMEFRAME_INTERVALS
from src.apps.market_data.repositories import TimescaleContinuousAggregateRepository
from src.apps.patterns.domain.regime import (
    calculate_regime_map,
    primary_regime,
    read_regime_details,
    serialize_regime_map,
)
from src.apps.patterns.domain.scheduler import should_request_analysis
from src.apps.patterns.domain.semantics import is_cluster_signal, is_pattern_signal
from src.core.db.session import async_engine
from src.core.db.uow import BaseAsyncUnitOfWork


@dataclass(slots=True, frozen=True)
class IndicatorMetricsUpdate:
    coin_id: int
    activity_score: float | None = None
    activity_bucket: str | None = None
    analysis_priority: int | None = None
    market_regime: str | None = None
    market_regime_details: dict[str, object] | None = None
    price_change_24h: float | None = None
    price_change_7d: float | None = None
    volatility: float | None = None


@dataclass(slots=True, frozen=True)
class IndicatorEventItem:
    coin_id: int
    timeframe: int
    timestamp: datetime
    feature_source: str
    activity_score: float | None
    activity_bucket: str | None
    analysis_priority: int | None
    market_regime: str | None
    regime_confidence: float | None
    price_change_24h: float | None
    price_change_7d: float | None
    volatility: float | None
    classic_signals: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class IndicatorEventResult:
    status: str
    coin_id: int
    symbol: str | None = None
    reason: str | None = None
    timeframes: tuple[int, ...] = ()
    indicator_version: int = INDICATOR_VERSION
    items: tuple[IndicatorEventItem, ...] = ()


@dataclass(slots=True, frozen=True)
class FeatureSnapshotCaptureResult:
    status: str
    coin_id: int
    timeframe: int
    timestamp: datetime
    reason: str | None = None
    price_current: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    trend_score: int | None = None
    volatility: float | None = None
    sector_strength: float | None = None
    market_regime: str | None = None
    cycle_phase: str | None = None
    pattern_density: int = 0
    cluster_score: float = 0.0


@dataclass(slots=True, frozen=True)
class AnalysisScheduleResult:
    should_publish: bool
    activity_bucket: str | None
    state_updated: bool


def _regime_for_timeframe(
    *,
    timeframe: int,
    regime_map: dict[int, object],
    fallback: str | None,
) -> tuple[str | None, float | None]:
    regime = regime_map.get(timeframe)
    if regime is None:
        return fallback, None
    return str(regime.regime), float(regime.confidence)


class IndicatorReadService:
    def __init__(self, session: AsyncSession) -> None:
        self._queries = IndicatorQueryService(session)
        self._signals = IndicatorSignalRepository(session)

    async def list_coin_metrics(self) -> tuple[CoinMetricsReadModel, ...]:
        return await self._queries.list_coin_metrics()

    async def list_signals(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> tuple[SignalSummaryReadModel, ...]:
        return await self._queries.list_signals(symbol=symbol, timeframe=timeframe, limit=limit)

    async def list_signal_types_at_timestamp(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object,
    ) -> set[str]:
        return await self._signals.list_types_at_timestamp(
            coin_id=coin_id,
            timeframe=timeframe,
            candle_timestamp=candle_timestamp,
        )

    async def get_market_radar(self, *, limit: int = 8) -> MarketRadarReadModel:
        return await self._queries.get_market_radar(limit=limit)

    async def get_market_flow(self, *, limit: int = 8, timeframe: int = 60) -> MarketFlowReadModel:
        return await self._queries.get_market_flow(limit=limit, timeframe=timeframe)


class IndicatorAnalyticsService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._coins = IndicatorCoinRepository(uow.session)
        self._candles = IndicatorCandleRepository(uow.session)
        self._metrics = IndicatorMetricsRepository(uow.session)
        self._cache = IndicatorCacheRepository(uow.session)
        self._signals = IndicatorSignalRepository(uow.session)
        self._feature_flags = IndicatorFeatureFlagRepository(uow.session)
        self._aggregates = TimescaleContinuousAggregateRepository(async_engine)

    async def process_event(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
    ) -> IndicatorEventResult:
        event = CandleAnalyticsEvent(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            timestamp=ensure_utc(timestamp),
        )
        coin = await self._coins.get_by_id(event.coin_id)
        if coin is None or coin.deleted_at is not None:
            return IndicatorEventResult(status="skipped", coin_id=event.coin_id, reason="coin_not_found")

        base_timeframe = _coin_base_timeframe(coin)
        base_window_start, base_window_end = await self._candles.get_base_bounds(coin_id=int(coin.id))
        if base_window_start is not None and base_window_end is not None:
            for aggregate_timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
                if not await self._candles.aggregate_has_rows(coin_id=int(coin.id), timeframe=aggregate_timeframe):
                    await self._aggregates.refresh_range(
                        timeframe=aggregate_timeframe,
                        window_start=base_window_start,
                        window_end=base_window_end,
                    )

        affected_timeframes = determine_affected_timeframes(timeframe=event.timeframe, timestamp=event.timestamp)
        for affected_timeframe in affected_timeframes:
            if affected_timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
                await self._aggregates.refresh_range(
                    timeframe=affected_timeframe,
                    window_start=event.timestamp,
                    window_end=event.timestamp,
                )

        snapshots: dict[int, TimeframeSnapshot] = {}
        for current_timeframe in TIMEFRAME_INTERVALS:
            candles = await self._candles.fetch_points(
                coin_id=int(coin.id),
                timeframe=current_timeframe,
                limit=PRICE_HISTORY_LOOKBACK_BARS,
            )
            feature_source = (
                "candles"
                if await self._candles.has_direct_candles(coin_id=int(coin.id), timeframe=current_timeframe)
                or base_timeframe != BASE_TIMEFRAME_MINUTES
                else AGGREGATE_VIEW_BY_TIMEFRAME.get(current_timeframe, "candles")
            )
            snapshot = _calculate_snapshot(candles, current_timeframe, feature_source=feature_source)
            if snapshot is not None:
                snapshots[current_timeframe] = snapshot

        base_candles = await self._candles.fetch_points(
            coin_id=int(coin.id),
            timeframe=base_timeframe,
            limit=800,
        )
        volume_24h, volume_change_24h, volatility = _compute_volume_metrics(base_candles, base_timeframe)
        primary = _select_primary_snapshot(snapshots)
        base_snapshot = snapshots.get(base_timeframe)
        price_change_7d = _compute_price_change(base_candles, timedelta(days=7))
        regime_map = (
            calculate_regime_map(snapshots, volatility=volatility, price_change_7d=price_change_7d)
            if await self._feature_flags.is_enabled("market_regime_engine")
            else {}
        )
        metrics_payload = await self._upsert_coin_metrics(
            coin=coin,
            base_timeframe=base_timeframe,
            primary=primary,
            base_snapshot=base_snapshot,
            base_candles=base_candles,
            volume_24h=volume_24h,
            volume_change_24h=volume_change_24h,
            volatility=volatility,
            refresh_market_cap=240 in affected_timeframes or 1440 in affected_timeframes,
            market_regime=(
                str(regime_map[primary.timeframe].regime)
                if primary is not None and primary.timeframe in regime_map
                else primary_regime(regime_map)
            ),
            market_regime_details=serialize_regime_map(regime_map) if regime_map else None,
        )
        await self._cache.upsert_snapshots(
            coin_id=int(coin.id),
            snapshots=[
                snapshots[current_timeframe]
                for current_timeframe in affected_timeframes
                if current_timeframe in snapshots
            ],
            volume_24h=volume_24h,
            volume_change_24h=volume_change_24h,
        )

        items: list[IndicatorEventItem] = []
        for affected_timeframe in affected_timeframes:
            snapshot = snapshots.get(affected_timeframe)
            if snapshot is None:
                continue
            before_signal_types = await self._signals.list_types_at_timestamp(
                coin_id=int(coin.id),
                timeframe=affected_timeframe,
                candle_timestamp=snapshot.candle_close_timestamp,
            )
            await self._signals.insert_known_signals(
                coin_id=int(coin.id),
                timeframe=affected_timeframe,
                signals=_detect_signals(snapshot),
            )
            after_signal_types = await self._signals.list_types_at_timestamp(
                coin_id=int(coin.id),
                timeframe=affected_timeframe,
                candle_timestamp=snapshot.candle_close_timestamp,
            )
            regime_name, regime_confidence = _regime_for_timeframe(
                timeframe=affected_timeframe,
                regime_map=regime_map,
                fallback=metrics_payload.market_regime,
            )
            items.append(
                IndicatorEventItem(
                    coin_id=int(coin.id),
                    timeframe=affected_timeframe,
                    timestamp=snapshot.candle_close_timestamp,
                    feature_source=snapshot.feature_source,
                    activity_score=metrics_payload.activity_score,
                    activity_bucket=metrics_payload.activity_bucket,
                    analysis_priority=metrics_payload.analysis_priority,
                    market_regime=regime_name,
                    regime_confidence=regime_confidence,
                    price_change_24h=metrics_payload.price_change_24h,
                    price_change_7d=metrics_payload.price_change_7d,
                    volatility=metrics_payload.volatility,
                    classic_signals=tuple(
                        sorted(
                            signal_type
                            for signal_type in (after_signal_types - before_signal_types)
                            if signal_type in self._known_signal_types
                        )
                    ),
                )
            )

        return IndicatorEventResult(
            status="ok",
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            timeframes=tuple(affected_timeframes),
            items=tuple(items),
        )

    @property
    def _known_signal_types(self) -> set[str]:
        from src.apps.indicators.analytics import SIGNAL_TYPES

        return SIGNAL_TYPES

    async def _upsert_coin_metrics(
        self,
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
    ) -> IndicatorMetricsUpdate:
        await self._metrics.ensure_row(int(coin.id))
        if primary is None:
            return IndicatorMetricsUpdate(
                coin_id=int(coin.id),
                market_regime=market_regime,
                market_regime_details=market_regime_details,
            )

        trend = _compute_trend(primary)
        trend_score = _compute_trend_score(primary, volume_change_24h)
        existing_market_cap = await self._metrics.get_market_cap(int(coin.id))
        price_current = base_snapshot.price_current if base_snapshot is not None else primary.price_current
        price_change_1h = _compute_price_change(base_candles, timedelta(hours=1))
        price_change_24h = _compute_price_change(base_candles, timedelta(hours=24))
        price_change_7d = _compute_price_change(base_candles, timedelta(days=7))
        activity_score, activity_bucket, analysis_priority = _activity_fields(
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
            "market_cap": await _fetch_market_cap(coin.symbol)
            if refresh_market_cap or existing_market_cap is None
            else existing_market_cap,
            "trend": trend,
            "trend_score": trend_score,
            "activity_score": activity_score,
            "activity_bucket": activity_bucket,
            "analysis_priority": analysis_priority,
            "market_regime": market_regime or _compute_market_regime(primary, trend, volume_change_24h),
            "market_regime_details": market_regime_details,
            "indicator_version": INDICATOR_VERSION,
            "updated_at": utc_now(),
        }
        await self._metrics.upsert(payload)
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


class FeatureSnapshotService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._coins = IndicatorCoinRepository(uow.session)
        self._metrics = IndicatorMetricsRepository(uow.session)
        self._signals = IndicatorSignalRepository(uow.session)
        self._feature_snapshots = IndicatorFeatureSnapshotRepository(uow.session)
        self._sector_metrics = IndicatorSectorMetricRepository(uow.session)
        self._market_cycles = IndicatorMarketCycleRepository(uow.session)

    async def capture_snapshot(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
        price_current: float | None,
        rsi_14: float | None,
        macd: float | None,
    ) -> FeatureSnapshotCaptureResult:
        normalized_timestamp = ensure_utc(timestamp)
        coin = await self._coins.get_by_id(coin_id)
        if coin is None or coin.deleted_at is not None:
            return FeatureSnapshotCaptureResult(
                status="skipped",
                reason="coin_not_found",
                coin_id=coin_id,
                timeframe=timeframe,
                timestamp=normalized_timestamp,
            )

        metrics = await self._metrics.get_by_coin_id(coin_id)
        sector_metric = (
            await self._sector_metrics.get_by_key(sector_id=int(coin.sector_id), timeframe=timeframe)
            if coin.sector_id is not None
            else None
        )
        cycle = await self._market_cycles.get_by_key(coin_id=coin_id, timeframe=timeframe)
        signal_rows = await self._signals.list_pattern_signal_rows(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=normalized_timestamp,
        )
        pattern_density = sum(1 for row in signal_rows if is_pattern_signal(str(row.signal_type)))
        cluster_score = sum(
            float(row.priority_score or row.confidence or 0.0)
            for row in signal_rows
            if is_cluster_signal(str(row.signal_type))
        )
        regime_snapshot = (
            read_regime_details(metrics.market_regime_details, timeframe)
            if metrics is not None and metrics.market_regime_details
            else None
        )
        payload = FeatureSnapshotPayload(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=normalized_timestamp,
            price_current=price_current,
            rsi_14=rsi_14,
            macd=macd,
            trend_score=metrics.trend_score if metrics is not None else None,
            volatility=float(metrics.volatility) if metrics is not None and metrics.volatility is not None else None,
            sector_strength=(
                float(sector_metric.sector_strength)
                if sector_metric is not None and sector_metric.sector_strength is not None
                else None
            ),
            market_regime=(
                str(regime_snapshot.regime)
                if regime_snapshot is not None
                else (str(metrics.market_regime) if metrics is not None and metrics.market_regime is not None else None)
            ),
            cycle_phase=str(cycle.cycle_phase) if cycle is not None and cycle.cycle_phase is not None else None,
            pattern_density=pattern_density,
            cluster_score=cluster_score,
        )
        await self._feature_snapshots.upsert(payload)
        return FeatureSnapshotCaptureResult(
            status="ok",
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=normalized_timestamp,
            price_current=payload.price_current,
            rsi_14=payload.rsi_14,
            macd=payload.macd,
            trend_score=payload.trend_score,
            volatility=payload.volatility,
            sector_strength=payload.sector_strength,
            market_regime=payload.market_regime,
            cycle_phase=payload.cycle_phase,
            pattern_density=payload.pattern_density,
            cluster_score=payload.cluster_score,
        )


class AnalysisSchedulerService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._metrics = IndicatorMetricsRepository(uow.session)

    async def evaluate_indicator_update(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
        activity_bucket_hint: str | None,
    ) -> AnalysisScheduleResult:
        normalized_timestamp = ensure_utc(timestamp)
        metrics = await self._metrics.get_by_coin_id(int(coin_id))
        activity_bucket = (
            str(activity_bucket_hint)
            if activity_bucket_hint is not None
            else (str(metrics.activity_bucket) if metrics is not None and metrics.activity_bucket is not None else None)
        )
        should_publish = should_request_analysis(
            timeframe=int(timeframe),
            timestamp=normalized_timestamp,
            activity_bucket=activity_bucket,
            last_analysis_at=metrics.last_analysis_at if metrics is not None else None,
        )
        if not should_publish:
            return AnalysisScheduleResult(
                should_publish=False,
                activity_bucket=activity_bucket,
                state_updated=False,
            )
        if metrics is None:
            return AnalysisScheduleResult(
                should_publish=True,
                activity_bucket=activity_bucket,
                state_updated=False,
            )
        metrics.last_analysis_at = normalized_timestamp
        return AnalysisScheduleResult(
            should_publish=True,
            activity_bucket=activity_bucket,
            state_updated=True,
        )


__all__ = [
    "AnalysisScheduleResult",
    "AnalysisSchedulerService",
    "FeatureSnapshotCaptureResult",
    "FeatureSnapshotService",
    "IndicatorAnalyticsService",
    "IndicatorEventItem",
    "IndicatorEventResult",
    "IndicatorMetricsUpdate",
    "determine_affected_timeframes",
    "IndicatorReadService",
]
