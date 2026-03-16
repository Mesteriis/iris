from datetime import datetime, timedelta

from src.apps.patterns.domain.base import PatternDetection
from src.apps.patterns.domain.pattern_context import apply_pattern_context, dependencies_satisfied
from src.apps.patterns.domain.success import apply_pattern_success_validation
from src.apps.patterns.domain.utils import current_indicator_map
from src.apps.patterns.engines import build_pattern_cluster_specs, build_pattern_hierarchy_specs
from src.apps.patterns.repositories import PatternMarketCycleRepository, PatternSignalRepository
from src.apps.patterns.runtime_results import (
    PatternIncrementalDetectionStepResult,
    PatternIncrementalSignalsResult,
    PatternMarketCycleUpdateResult,
    PatternRegimeRefreshResult,
    PatternSignalDerivationResult,
)
from src.apps.patterns.runtime_steps import update_market_cycle_step
from src.apps.patterns.runtime_support import (
    build_detection_rows,
    build_signal_rows_from_specs,
    normalize_runtime_timestamp,
)
from src.apps.patterns.task_service_base import PatternTaskBase
from src.apps.patterns.task_service_market import PatternMarketDiscoveryMixin
from src.core.db.uow import BaseAsyncUnitOfWork


class PatternRealtimeService(PatternMarketDiscoveryMixin, PatternTaskBase):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternRealtimeService")
        self._cycles = PatternMarketCycleRepository(uow.session)
        self._signals = PatternSignalRepository(uow.session)

    async def detect_incremental_signals(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None = None,
        regime: str | None = None,
        lookback: int = 200,
    ) -> PatternIncrementalSignalsResult:
        normalized_timestamp = normalize_runtime_timestamp(candle_timestamp)
        existing_signal_types = set(
            await self._queries.list_signal_types_at_timestamp(
                coin_id=coin_id,
                timeframe=timeframe,
                timestamp=normalized_timestamp,
            )
        )
        detection_result = await self._detect_incremental_patterns(
            coin_id=coin_id,
            timeframe=timeframe,
            regime=regime,
            lookback=lookback,
        )
        cluster_result = await self._build_pattern_clusters(
            coin_id=coin_id,
            timeframe=timeframe,
            candle_timestamp=normalized_timestamp,
        )
        hierarchy_result = await self._build_hierarchy_signals(
            coin_id=coin_id,
            timeframe=timeframe,
            candle_timestamp=normalized_timestamp,
        )
        current_signal_types = set(
            await self._queries.list_signal_types_at_timestamp(
                coin_id=coin_id,
                timeframe=timeframe,
                timestamp=normalized_timestamp,
            )
        )
        new_signal_types = tuple(sorted(current_signal_types - existing_signal_types))
        requires_commit = any(
            item.created > 0
            for item in (detection_result, cluster_result, hierarchy_result)
            if item.status == "ok"
        )
        return PatternIncrementalSignalsResult(
            status="ok",
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            new_signal_types=new_signal_types,
            requires_commit=requires_commit,
            detection=detection_result,
            clusters=cluster_result,
            hierarchy=hierarchy_result,
        )

    async def refresh_regime_state(
        self,
        *,
        coin_id: int,
        timeframe: int,
        regime: str | None,
        regime_confidence: float,
    ) -> PatternRegimeRefreshResult | None:
        coin = await self._coins.get_by_id(int(coin_id))
        if coin is None:
            return None
        await self._refresh_sector_metrics(timeframe=int(timeframe))
        cycle_before = await self._cycles.get(coin_id=int(coin_id), timeframe=int(timeframe))
        cycle_result = await self._update_market_cycle(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
        )
        return PatternRegimeRefreshResult(
            status="ok",
            requires_commit=True,
            previous_cycle=cycle_before.cycle_phase if cycle_before is not None else None,
            next_cycle=cycle_result.cycle_phase,
            regime=regime,
            regime_confidence=float(regime_confidence),
        )

    async def _detect_incremental_patterns(
        self,
        *,
        coin_id: int,
        timeframe: int,
        regime: str | None,
        lookback: int,
    ) -> PatternIncrementalDetectionStepResult:
        if not await self._feature_enabled("pattern_detection"):
            return PatternIncrementalDetectionStepResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="pattern_detection_disabled",
            )
        candles = await self._fetch_candle_points(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            limit=max(int(lookback), 30),
        )
        if len(candles) < 30:
            return PatternIncrementalDetectionStepResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="insufficient_candles",
            )

        detectors = await self._load_active_detectors(timeframe=int(timeframe))
        if not detectors:
            return PatternIncrementalDetectionStepResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="detectors_not_found",
            )
        indicators = current_indicator_map(candles)
        success_cache = await self._pattern_success_cache(
            timeframe=int(timeframe),
            slugs={detector.slug for detector in detectors},
            regimes={str(regime)} if regime is not None else set(),
        )
        detections: list[PatternDetection] = []
        for detector in detectors:
            if not detector.enabled or int(timeframe) not in detector.supported_timeframes:
                continue
            if not dependencies_satisfied(detector, indicators):
                continue
            for detection in detector.detect(candles, indicators):
                adjusted = apply_pattern_context(
                    detection=detection,
                    detector=detector,
                    indicators=indicators,
                    regime=regime,
                )
                if adjusted is None:
                    continue
                detection_regime = (
                    str(adjusted.attributes.get("regime")) if adjusted.attributes.get("regime") is not None else regime
                )
                validated = apply_pattern_success_validation(
                    detection=adjusted,
                    timeframe=int(timeframe),
                    market_regime=detection_regime,
                    coin_id=int(coin_id),
                    emit_events=True,
                    snapshot_cache=success_cache,
                )
                if validated is not None:
                    detections.append(validated)
        rows = build_detection_rows(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            detections=detections,
        )
        created = await self._upsert_signals(rows=rows)
        return PatternIncrementalDetectionStepResult(
            status="ok",
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            detections=len(detections),
            created=created,
        )

    async def _build_pattern_clusters(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: datetime,
    ) -> PatternSignalDerivationResult:
        if not await self._feature_enabled("pattern_clusters"):
            return PatternSignalDerivationResult(status="skipped", reason="pattern_clusters_disabled")
        signals = await self._queries.list_runtime_signal_snapshots_at_timestamp(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            timestamp=candle_timestamp,
        )
        if not signals:
            return PatternSignalDerivationResult(status="skipped", reason="pattern_signals_not_found")
        metrics = await self._queries.get_coin_metrics_snapshot(coin_id=int(coin_id))
        specs = build_pattern_cluster_specs(signals=signals, metrics=metrics)
        created = await self._signals.insert_new(
            rows=build_signal_rows_from_specs(
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                candle_timestamp=candle_timestamp,
                specs=specs,
            )
        )
        await self._uow.flush()
        return PatternSignalDerivationResult(status="ok", created=created, specs=specs)

    async def _build_hierarchy_signals(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: datetime,
    ) -> PatternSignalDerivationResult:
        if not await self._feature_enabled("pattern_hierarchy"):
            return PatternSignalDerivationResult(status="skipped", reason="pattern_hierarchy_disabled")
        window_start = candle_timestamp - timedelta(days=14)
        signals = await self._queries.list_runtime_signal_snapshots_between(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            window_start=window_start,
            window_end=candle_timestamp,
        )
        if not signals:
            return PatternSignalDerivationResult(status="skipped", reason="pattern_signals_not_found")
        metrics = await self._queries.get_coin_metrics_snapshot(coin_id=int(coin_id))
        specs = build_pattern_hierarchy_specs(
            signals=signals,
            has_cluster_signals=any(signal.signal_type.startswith("pattern_cluster_") for signal in signals),
            metrics=metrics,
        )
        created = await self._signals.insert_new(
            rows=build_signal_rows_from_specs(
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                candle_timestamp=candle_timestamp,
                specs=specs,
            )
        )
        await self._uow.flush()
        return PatternSignalDerivationResult(status="ok", created=created, specs=specs)

    async def _update_market_cycle(
        self,
        *,
        coin_id: int,
        timeframe: int,
    ) -> PatternMarketCycleUpdateResult:
        return await update_market_cycle_step(
            queries=self._queries,
            cycles=self._cycles,
            uow=self._uow,
            coin_id=int(coin_id),
            timeframe=int(timeframe),
        )
