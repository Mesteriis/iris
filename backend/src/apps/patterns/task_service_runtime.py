from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from src.apps.cross_market.models import SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.patterns.domain.base import PatternDetection
from src.apps.patterns.domain.cycle import _detect_cycle_phase
from src.apps.patterns.domain.pattern_context import apply_pattern_context, dependencies_satisfied
from src.apps.patterns.domain.regime import read_regime_details
from src.apps.patterns.domain.semantics import (
    BEARISH_PATTERN_SLUGS,
    BULLISH_PATTERN_SLUGS,
    is_cluster_signal,
    is_pattern_signal,
    slug_from_signal_type,
)
from src.apps.patterns.domain.success import apply_pattern_success_validation
from src.apps.patterns.domain.utils import current_indicator_map
from src.apps.patterns.models import MarketCycle
from src.apps.patterns.task_service_base import PatternTaskBase
from src.apps.patterns.task_service_market import PatternMarketDiscoveryMixin
from src.apps.signals.models import Signal
from src.core.db.uow import BaseAsyncUnitOfWork


class PatternRealtimeService(PatternMarketDiscoveryMixin, PatternTaskBase):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternRealtimeService")

    async def detect_incremental_signals(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None = None,
        regime: str | None = None,
        lookback: int = 200,
    ) -> dict[str, object]:
        normalized_timestamp = self._normalize_timestamp(candle_timestamp)
        existing_signal_types = await self._signal_types_at_timestamp(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=normalized_timestamp,
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
        current_signal_types = await self._signal_types_at_timestamp(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=normalized_timestamp,
        )
        new_signal_types = tuple(sorted(current_signal_types - existing_signal_types))
        requires_commit = any(
            int(item.get("created", 0)) > 0
            for item in (detection_result, cluster_result, hierarchy_result)
            if item.get("status") == "ok"
        )
        return {
            "status": "ok",
            "coin_id": int(coin_id),
            "timeframe": int(timeframe),
            "new_signal_types": new_signal_types,
            "requires_commit": requires_commit,
            "detection": detection_result,
            "clusters": cluster_result,
            "hierarchy": hierarchy_result,
        }

    async def refresh_regime_state(
        self,
        *,
        coin_id: int,
        timeframe: int,
        regime: str | None,
        regime_confidence: float,
    ) -> dict[str, object] | None:
        coin = await self._coins.get_by_id(int(coin_id))
        if coin is None:
            return None
        await self._refresh_sector_metrics(timeframe=int(timeframe))
        cycle_before = await self.session.get(MarketCycle, (int(coin_id), int(timeframe)))
        cycle_result = await self._update_market_cycle(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
        )
        return {
            "status": "ok",
            "requires_commit": True,
            "previous_cycle": cycle_before.cycle_phase if cycle_before is not None else None,
            "next_cycle": cycle_result.get("cycle_phase"),
            "regime": regime,
            "regime_confidence": float(regime_confidence),
        }

    async def _detect_incremental_patterns(
        self,
        *,
        coin_id: int,
        timeframe: int,
        regime: str | None,
        lookback: int,
    ) -> dict[str, object]:
        if not await self._feature_enabled("pattern_detection"):
            return {
                "status": "skipped",
                "reason": "pattern_detection_disabled",
                "coin_id": int(coin_id),
                "timeframe": int(timeframe),
            }
        candles = await self._fetch_candle_points(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            limit=max(int(lookback), 30),
        )
        if len(candles) < 30:
            return {
                "status": "skipped",
                "reason": "insufficient_candles",
                "coin_id": int(coin_id),
                "timeframe": int(timeframe),
            }

        detectors = await self._load_active_detectors(timeframe=int(timeframe))
        if not detectors:
            return {
                "status": "skipped",
                "reason": "detectors_not_found",
                "coin_id": int(coin_id),
                "timeframe": int(timeframe),
            }
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
                    cast(Any, None),
                    detection=adjusted,
                    timeframe=int(timeframe),
                    market_regime=detection_regime,
                    coin_id=int(coin_id),
                    emit_events=True,
                    snapshot_cache=success_cache,
                )
                if validated is not None:
                    detections.append(validated)
        rows = [
            {
                "coin_id": int(coin_id),
                "timeframe": int(timeframe),
                "signal_type": detection.signal_type,
                "confidence": detection.confidence,
                "priority_score": 0.0,
                "context_score": 1.0,
                "regime_alignment": 1.0,
                "market_regime": str(detection.attributes.get("regime"))
                if detection.attributes.get("regime") is not None
                else None,
                "candle_timestamp": detection.candle_timestamp,
            }
            for detection in detections
        ]
        created = await self._upsert_signals(rows=rows)
        return {
            "status": "ok",
            "coin_id": int(coin_id),
            "timeframe": int(timeframe),
            "detections": len(detections),
            "created": created,
        }

    async def _build_pattern_clusters(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: datetime,
    ) -> dict[str, object]:
        if not await self._feature_enabled("pattern_clusters"):
            return {"status": "skipped", "reason": "pattern_clusters_disabled"}
        signals = (
            (
                await self.session.execute(
                    select(Signal).where(
                        Signal.coin_id == int(coin_id),
                        Signal.timeframe == int(timeframe),
                        Signal.candle_timestamp == candle_timestamp,
                    )
                )
            )
            .scalars()
            .all()
        )
        pattern_signals = [signal for signal in signals if is_pattern_signal(self._signal_type_value(signal.signal_type))]
        if not pattern_signals:
            return {"status": "skipped", "reason": "pattern_signals_not_found"}
        bullish = [
            signal
            for signal in pattern_signals
            if (slug_from_signal_type(self._signal_type_value(signal.signal_type)) or "") in BULLISH_PATTERN_SLUGS
        ]
        bearish = [
            signal
            for signal in pattern_signals
            if (slug_from_signal_type(self._signal_type_value(signal.signal_type)) or "") in BEARISH_PATTERN_SLUGS
        ]
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(coin_id)).limit(1))
        rows: list[dict[str, object]] = []
        if (
            bullish
            and any(self._signal_type_value(signal.signal_type) == "pattern_volume_spike" for signal in pattern_signals)
            and metrics is not None
            and int(metrics.trend_score or 0) >= 60
        ):
            confidence = min(sum(float(signal.confidence) for signal in bullish) / len(bullish) + 0.12, 0.95)
            rows.append(
                {
                    "coin_id": int(coin_id),
                    "timeframe": int(timeframe),
                    "signal_type": "pattern_cluster_bullish",
                    "confidence": float(confidence),
                    "priority_score": 0.0,
                    "context_score": 1.0,
                    "regime_alignment": 1.0,
                    "market_regime": str(metrics.market_regime) if metrics.market_regime is not None else None,
                    "candle_timestamp": candle_timestamp,
                }
            )
        if (
            bearish
            and any(
                self._signal_type_value(signal.signal_type) in {"pattern_volume_spike", "pattern_volume_climax"}
                for signal in pattern_signals
            )
            and metrics is not None
            and int(metrics.trend_score or 100) <= 40
        ):
            confidence = min(sum(float(signal.confidence) for signal in bearish) / len(bearish) + 0.12, 0.95)
            rows.append(
                {
                    "coin_id": int(coin_id),
                    "timeframe": int(timeframe),
                    "signal_type": "pattern_cluster_bearish",
                    "confidence": float(confidence),
                    "priority_score": 0.0,
                    "context_score": 1.0,
                    "regime_alignment": 1.0,
                    "market_regime": str(metrics.market_regime) if metrics.market_regime is not None else None,
                    "candle_timestamp": candle_timestamp,
                }
            )
        created = await self._insert_new_signals(rows=rows)
        return {"status": "ok", "created": created}

    async def _build_hierarchy_signals(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: datetime,
    ) -> dict[str, object]:
        if not await self._feature_enabled("pattern_hierarchy"):
            return {"status": "skipped", "reason": "pattern_hierarchy_disabled"}
        window_start = candle_timestamp - timedelta(days=14)
        signals = (
            (
                await self.session.execute(
                    select(Signal).where(
                        Signal.coin_id == int(coin_id),
                        Signal.timeframe == int(timeframe),
                        Signal.candle_timestamp >= window_start,
                        Signal.candle_timestamp <= candle_timestamp,
                    )
                )
            )
            .scalars()
            .all()
        )
        pattern_signals = [signal for signal in signals if is_pattern_signal(self._signal_type_value(signal.signal_type))]
        cluster_signals = [signal for signal in signals if is_cluster_signal(self._signal_type_value(signal.signal_type))]
        if not pattern_signals:
            return {"status": "skipped", "reason": "pattern_signals_not_found"}
        bullish = sum(
            1
            for signal in pattern_signals
            if (slug_from_signal_type(self._signal_type_value(signal.signal_type)) or "") in BULLISH_PATTERN_SLUGS
        )
        bearish = sum(
            1
            for signal in pattern_signals
            if (slug_from_signal_type(self._signal_type_value(signal.signal_type)) or "") in BEARISH_PATTERN_SLUGS
        )
        exhaustion = sum(
            1
            for signal in pattern_signals
            if self._signal_type_value(signal.signal_type) in {"pattern_momentum_exhaustion", "pattern_volume_climax"}
        )
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(coin_id)).limit(1))
        rows: list[dict[str, object]] = []
        market_regime = str(metrics.market_regime) if metrics is not None and metrics.market_regime is not None else None
        if metrics is not None and int(metrics.trend_score or 50) >= 55 and bullish >= 2 and cluster_signals:
            rows.append(
                {
                    "coin_id": int(coin_id),
                    "timeframe": int(timeframe),
                    "signal_type": "pattern_hierarchy_trend_continuation",
                    "confidence": 0.78,
                    "priority_score": 0.0,
                    "context_score": 1.0,
                    "regime_alignment": 1.0,
                    "market_regime": market_regime,
                    "candle_timestamp": candle_timestamp,
                }
            )
        if metrics is not None and int(metrics.trend_score or 50) <= 45 and bearish >= 2 and cluster_signals:
            rows.append(
                {
                    "coin_id": int(coin_id),
                    "timeframe": int(timeframe),
                    "signal_type": "pattern_hierarchy_distribution",
                    "confidence": 0.74,
                    "priority_score": 0.0,
                    "context_score": 1.0,
                    "regime_alignment": 1.0,
                    "market_regime": market_regime,
                    "candle_timestamp": candle_timestamp,
                }
            )
        if (
            metrics is not None
            and float(metrics.volatility or 0.0) < float(metrics.price_current or 1.0) * 0.03
            and bullish >= bearish
            and bullish >= 2
        ):
            rows.append(
                {
                    "coin_id": int(coin_id),
                    "timeframe": int(timeframe),
                    "signal_type": "pattern_hierarchy_accumulation",
                    "confidence": 0.7,
                    "priority_score": 0.0,
                    "context_score": 1.0,
                    "regime_alignment": 1.0,
                    "market_regime": market_regime,
                    "candle_timestamp": candle_timestamp,
                }
            )
        if exhaustion >= 2:
            rows.append(
                {
                    "coin_id": int(coin_id),
                    "timeframe": int(timeframe),
                    "signal_type": "pattern_hierarchy_trend_exhaustion",
                    "confidence": 0.73,
                    "priority_score": 0.0,
                    "context_score": 1.0,
                    "regime_alignment": 1.0,
                    "market_regime": market_regime,
                    "candle_timestamp": candle_timestamp,
                }
            )
        created = await self._insert_new_signals(rows=rows)
        return {"status": "ok", "created": created}

    async def _update_market_cycle(
        self,
        *,
        coin_id: int,
        timeframe: int,
    ) -> dict[str, object]:
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(coin_id)).limit(1))
        if metrics is None:
            return {"status": "skipped", "reason": "coin_metrics_not_found", "coin_id": int(coin_id)}
        pattern_density = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Signal)
                    .where(
                        Signal.coin_id == int(coin_id),
                        Signal.timeframe == int(timeframe),
                        Signal.signal_type.like("pattern_%"),
                        ~Signal.signal_type.like("pattern_cluster_%"),
                        ~Signal.signal_type.like("pattern_hierarchy_%"),
                    )
                )
            ).scalar_one()
            or 0
        )
        cluster_frequency = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Signal)
                    .where(
                        Signal.coin_id == int(coin_id),
                        Signal.timeframe == int(timeframe),
                        Signal.signal_type.like("pattern_cluster_%"),
                    )
                )
            ).scalar_one()
            or 0
        )
        sector_metric = None
        coin = await self._coins.get_by_id(int(coin_id))
        if coin is not None and coin.sector_id is not None:
            sector_metric = await self.session.get(SectorMetric, (int(coin.sector_id), int(timeframe)))
        regime_snapshot = read_regime_details(metrics.market_regime_details, int(timeframe))
        phase, confidence = _detect_cycle_phase(
            trend_score=metrics.trend_score,
            regime=regime_snapshot.regime if regime_snapshot is not None else metrics.market_regime,
            volatility=metrics.volatility,
            price_current=metrics.price_current,
            pattern_density=pattern_density,
            cluster_frequency=cluster_frequency,
            sector_strength=sector_metric.sector_strength if sector_metric is not None else None,
            capital_flow=sector_metric.capital_flow if sector_metric is not None else None,
        )
        stmt = insert(MarketCycle).values(
            {
                "coin_id": int(coin_id),
                "timeframe": int(timeframe),
                "cycle_phase": phase,
                "confidence": confidence,
                "detected_at": utc_now(),
            }
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe"],
            set_={
                "cycle_phase": stmt.excluded.cycle_phase,
                "confidence": stmt.excluded.confidence,
                "detected_at": stmt.excluded.detected_at,
            },
        )
        await self.session.execute(stmt)
        await self._uow.flush()
        return {
            "status": "ok",
            "coin_id": int(coin_id),
            "timeframe": int(timeframe),
            "cycle_phase": phase,
            "confidence": confidence,
        }

    async def _signal_types_at_timestamp(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
    ) -> set[str]:
        return set(
            self._signal_type_value(value)
            for value in (
                (
                    await self.session.execute(
                        select(Signal.signal_type).where(
                            Signal.coin_id == int(coin_id),
                            Signal.timeframe == int(timeframe),
                            Signal.candle_timestamp == timestamp,
                        )
                    )
                )
                .scalars()
                .all()
            )
        )

    async def _insert_new_signals(self, *, rows: list[dict[str, object]]) -> int:
        if not rows:
            return 0
        stmt = insert(Signal).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["coin_id", "timeframe", "candle_timestamp", "signal_type"],
        )
        result = await self.session.execute(stmt)
        await self._uow.flush()
        return int(result.rowcount or 0)

    @staticmethod
    def _normalize_timestamp(value: object | None) -> datetime:
        if value is None:
            return utc_now()
        if isinstance(value, datetime):
            return ensure_utc(value)
        if isinstance(value, str):
            return ensure_utc(datetime.fromisoformat(value))
        return utc_now()

    @staticmethod
    def _signal_type_value(value: object) -> str:
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, str):
            return enum_value
        return str(value)
