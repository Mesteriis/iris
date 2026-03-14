from __future__ import annotations

from datetime import datetime, timedelta

from src.apps.indicators.analysis_scheduler_service import AnalysisSchedulerService
from src.apps.indicators.analytics import (
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
from src.apps.indicators.feature_snapshot_service import FeatureSnapshotService
from src.apps.indicators.repositories import (
    IndicatorCacheRepository,
    IndicatorCandleRepository,
    IndicatorCoinRepository,
    IndicatorFeatureFlagRepository,
    IndicatorMetricsRepository,
    IndicatorSignalRepository,
)
from src.apps.indicators.results import (
    AnalysisScheduleResult,
    FeatureSnapshotCaptureResult,
    IndicatorEventItem,
    IndicatorEventResult,
    IndicatorMetricsUpdate,
)
from src.apps.indicators.service_support import (
    IndicatorAggregateRefresher,
    refresh_missing_aggregates,
    regime_for_timeframe,
    upsert_indicator_coin_metrics,
)
from src.apps.market_data.candles import AGGREGATE_VIEW_BY_TIMEFRAME, BASE_TIMEFRAME_MINUTES, TIMEFRAME_INTERVALS
from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.patterns.domain.regime import calculate_regime_map, primary_regime, serialize_regime_map
from src.core.db.uow import BaseAsyncUnitOfWork


class IndicatorAnalyticsService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._coins = IndicatorCoinRepository(uow.session)
        self._candles = IndicatorCandleRepository(uow.session)
        self._metrics = IndicatorMetricsRepository(uow.session)
        self._cache = IndicatorCacheRepository(uow.session)
        self._signals = IndicatorSignalRepository(uow.session)
        self._feature_flags = IndicatorFeatureFlagRepository(uow.session)
        self._aggregates = IndicatorAggregateRefresher()

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
        affected_timeframes = determine_affected_timeframes(timeframe=event.timeframe, timestamp=event.timestamp)
        await refresh_missing_aggregates(
            coin_id=int(coin.id),
            event_timestamp=event.timestamp,
            affected_timeframes=affected_timeframes,
            base_window_start=base_window_start,
            base_window_end=base_window_end,
            candles=self._candles,
            aggregates=self._aggregates,
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
            snapshots=[snapshots[current_timeframe] for current_timeframe in affected_timeframes if current_timeframe in snapshots],
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
            regime_name, regime_confidence = regime_for_timeframe(
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
        coin: object,
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
        return await upsert_indicator_coin_metrics(
            coin=coin,  # type: ignore[arg-type]
            base_timeframe=base_timeframe,
            primary=primary,
            base_snapshot=base_snapshot,
            base_candles=base_candles,
            volume_24h=volume_24h,
            volume_change_24h=volume_change_24h,
            volatility=volatility,
            refresh_market_cap=refresh_market_cap,
            market_regime=market_regime,
            market_regime_details=market_regime_details,
            metrics=self._metrics,
            activity_fields=_activity_fields,
            compute_market_regime=_compute_market_regime,
            compute_price_change=_compute_price_change,
            compute_trend=_compute_trend,
            compute_trend_score=_compute_trend_score,
            fetch_market_cap=_fetch_market_cap,
            now_fn=utc_now,
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
]
