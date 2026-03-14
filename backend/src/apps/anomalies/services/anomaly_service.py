from __future__ import annotations

from datetime import datetime

from src.apps.anomalies.constants import (
    ANOMALY_SOURCE_ENRICHMENT,
    ANOMALY_SOURCE_FAST_PATH,
    ANOMALY_SOURCE_MARKET_STRUCTURE_SCAN,
    ANOMALY_SOURCE_SECTOR_SCAN,
    ANOMALY_STATUS_ACTIVE,
    ANOMALY_STATUS_NEW,
    COOLDOWN_MINUTES,
    FAST_PATH_LOOKBACK,
    MARKET_STRUCTURE_LOOKBACK,
    SECTOR_SCAN_LOOKBACK,
)
from src.apps.anomalies.detection_runner import AnomalyDetectionRunner
from src.apps.anomalies.detectors import (
    CompressionExpansionDetector,
    CorrelationBreakdownDetector,
    CrossExchangeDislocationDetector,
    FailedBreakoutDetector,
    FundingOpenInterestDetector,
    LiquidationCascadeDetector,
    PriceSpikeDetector,
    PriceVolumeDivergenceDetector,
    RelativeDivergenceDetector,
    SynchronousMoveDetector,
    VolatilityBreakDetector,
    VolumeSpikeDetector,
)
from src.apps.anomalies.engines import build_enriched_anomaly_projection
from src.apps.anomalies.policies import AnomalyPolicyEngine
from src.apps.anomalies.repos import AnomalyRepo
from src.apps.anomalies.results import AnomalyDetectionBatchResult, AnomalyEnrichmentResult
from src.apps.anomalies.scoring import AnomalyScorer
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork


class AnomalyService(PersistenceComponent):
    def __init__(
        self,
        uow: BaseAsyncUnitOfWork,
        *,
        repo: AnomalyRepo | None = None,
        scorer: AnomalyScorer | None = None,
        policy_engine: AnomalyPolicyEngine | None = None,
    ) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="anomalies",
            component_name="AnomalyService",
        )
        self._uow = uow
        self._repo = repo or AnomalyRepo(uow.session)
        self._scorer = scorer or AnomalyScorer()
        self._policy_engine = policy_engine or AnomalyPolicyEngine(cooldown_minutes=COOLDOWN_MINUTES)
        self._runner = AnomalyDetectionRunner(
            uow=uow,
            repo=self._repo,
            scorer=self._scorer,
            policy_engine=self._policy_engine,
        )
        self._fast_detectors = (
            PriceSpikeDetector(),
            VolumeSpikeDetector(),
            VolatilityBreakDetector(),
            FailedBreakoutDetector(),
            CompressionExpansionDetector(),
            PriceVolumeDivergenceDetector(),
            RelativeDivergenceDetector(),
            CorrelationBreakdownDetector(),
        )
        self._sector_detector = SynchronousMoveDetector()
        self._market_structure_detectors = (
            FundingOpenInterestDetector(),
            CrossExchangeDislocationDetector(),
            LiquidationCascadeDetector(),
        )

    async def process_candle_closed(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
        source: str | None = None,
    ) -> AnomalyDetectionBatchResult:
        self._log_debug(
            "service.process_candle_closed",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            source=source or ANOMALY_SOURCE_FAST_PATH,
        )
        context = await self._repo.load_fast_detection_context(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            lookback=FAST_PATH_LOOKBACK,
        )
        if context is None:
            self._log_debug("service.process_candle_closed.result", mode="write", created=0, reason="context_unavailable")
            return AnomalyDetectionBatchResult(status="skipped", reason="context_unavailable")
        result = await self._runner.run(
            context,
            detectors=self._fast_detectors,
            source_pipeline=ANOMALY_SOURCE_FAST_PATH,
            extra_payload={"source": source or ANOMALY_SOURCE_FAST_PATH},
        )
        self._log_debug("service.process_candle_closed.result", mode="write", created=result.created)
        return result

    async def scan_sector_synchrony(
        self,
        *,
        trigger_coin_id: int,
        timeframe: int,
        timestamp: datetime,
        trigger_anomaly_id: int | None = None,
    ) -> AnomalyDetectionBatchResult:
        self._log_debug(
            "service.scan_sector_synchrony",
            mode="write",
            trigger_coin_id=trigger_coin_id,
            timeframe=timeframe,
            trigger_anomaly_id=trigger_anomaly_id,
        )
        context = await self._repo.load_sector_detection_context(
            coin_id=trigger_coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            lookback=SECTOR_SCAN_LOOKBACK,
        )
        if context is None:
            self._log_debug("service.scan_sector_synchrony.result", mode="write", status="skipped", created=0)
            return AnomalyDetectionBatchResult(status="skipped", reason="context_unavailable")
        return await self._runner.run(
            context,
            detectors=(self._sector_detector,),
            source_pipeline=ANOMALY_SOURCE_SECTOR_SCAN,
            extra_payload={"trigger_anomaly_id": trigger_anomaly_id},
        )

    async def scan_market_structure(
        self,
        *,
        trigger_coin_id: int,
        timeframe: int,
        timestamp: datetime,
        trigger_anomaly_id: int | None = None,
    ) -> AnomalyDetectionBatchResult:
        self._log_debug(
            "service.scan_market_structure",
            mode="write",
            trigger_coin_id=trigger_coin_id,
            timeframe=timeframe,
            trigger_anomaly_id=trigger_anomaly_id,
        )
        context = await self._repo.load_market_structure_detection_context(
            coin_id=trigger_coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            lookback=MARKET_STRUCTURE_LOOKBACK,
        )
        if context is None:
            self._log_debug("service.scan_market_structure.result", mode="write", status="skipped", reason="context")
            return AnomalyDetectionBatchResult(status="skipped", reason="context_unavailable")
        if not context.venue_snapshots:
            self._log_debug(
                "service.scan_market_structure.result",
                mode="write",
                status="skipped",
                reason="market_structure_unavailable",
            )
            return AnomalyDetectionBatchResult(status="skipped", reason="market_structure_unavailable")
        return await self._runner.run(
            context,
            detectors=self._market_structure_detectors,
            source_pipeline=ANOMALY_SOURCE_MARKET_STRUCTURE_SCAN,
            extra_payload={"trigger_anomaly_id": trigger_anomaly_id},
        )

    async def enrich_anomaly(self, anomaly_id: int) -> AnomalyEnrichmentResult:
        self._log_debug("service.enrich_anomaly", mode="write", anomaly_id=anomaly_id)
        anomaly = await self._repo.get_for_update(anomaly_id)
        if anomaly is None:
            self._log_warning("service.enrich_anomaly.not_found", mode="write", anomaly_id=anomaly_id)
            return AnomalyEnrichmentResult(
                status="error",
                anomaly_id=int(anomaly_id),
                reason="anomaly_not_found",
            )

        portfolio_relevant = await self._repo.has_open_portfolio_position(int(anomaly.coin_id), int(anomaly.timeframe))
        sector_active_count = await self._repo.count_active_sector_anomalies(
            sector=anomaly.sector,
            timeframe=int(anomaly.timeframe),
        )
        projection = build_enriched_anomaly_projection(
            payload_json=dict(anomaly.payload_json or {}),
            portfolio_relevant=portfolio_relevant,
            market_wide=bool(dict(anomaly.payload_json or {}).get("context", {}).get("scope") == "sector" or sector_active_count > 1),
            enrichment_source=ANOMALY_SOURCE_ENRICHMENT,
        )
        await self._repo.touch_anomaly(
            anomaly,
            status=ANOMALY_STATUS_ACTIVE if anomaly.status == ANOMALY_STATUS_NEW else anomaly.status,
            payload_json=projection.payload_json,
        )
        self._log_info("service.enrich_anomaly.result", mode="write", anomaly_id=int(anomaly.id), status="ok")
        return AnomalyEnrichmentResult(
            status="ok",
            anomaly_id=int(anomaly.id),
            portfolio_relevant=projection.portfolio_relevant,
            market_wide=projection.market_wide,
        )
