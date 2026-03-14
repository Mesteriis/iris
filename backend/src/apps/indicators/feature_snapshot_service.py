from __future__ import annotations

from datetime import datetime

from src.apps.indicators.repositories import (
    FeatureSnapshotPayload,
    IndicatorCoinRepository,
    IndicatorFeatureSnapshotRepository,
    IndicatorMarketCycleRepository,
    IndicatorMetricsRepository,
    IndicatorSectorMetricRepository,
    IndicatorSignalRepository,
)
from src.apps.indicators.results import FeatureSnapshotCaptureResult
from src.apps.market_data.domain import ensure_utc
from src.apps.patterns.domain.regime import read_regime_details
from src.apps.patterns.domain.semantics import is_cluster_signal, is_pattern_signal
from src.core.db.uow import BaseAsyncUnitOfWork


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


__all__ = ["FeatureSnapshotService"]
