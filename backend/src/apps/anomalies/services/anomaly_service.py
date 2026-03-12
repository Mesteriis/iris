from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.anomalies.constants import (
    ANOMALY_EVENT_TYPE,
    ANOMALY_SOURCE_ENRICHMENT,
    ANOMALY_SOURCE_FAST_PATH,
    ANOMALY_SOURCE_MARKET_STRUCTURE_SCAN,
    ANOMALY_SOURCE_SECTOR_SCAN,
    ANOMALY_STATUS_ACTIVE,
    ANOMALY_STATUS_COOLING,
    ANOMALY_STATUS_NEW,
    ANOMALY_STATUS_RESOLVED,
    COOLDOWN_MINUTES,
    FAST_PATH_LOOKBACK,
    MARKET_STRUCTURE_LOOKBACK,
    SECTOR_SCAN_LOOKBACK,
)
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
    VolumeSpikeDetector,
    VolatilityBreakDetector,
)
from src.apps.anomalies.policies import AnomalyPolicyEngine
from src.apps.anomalies.repos import AnomalyRepo
from src.apps.anomalies.scoring import AnomalyScorer
from src.apps.anomalies.schemas import AnomalyDetectionContext, AnomalyDraft, DetectorFinding
from src.runtime.streams.publisher import publish_event


class AnomalyService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        repo: AnomalyRepo | None = None,
        scorer: AnomalyScorer | None = None,
        policy_engine: AnomalyPolicyEngine | None = None,
    ) -> None:
        self._session = session
        self._repo = repo or AnomalyRepo(session)
        self._scorer = scorer or AnomalyScorer()
        self._policy_engine = policy_engine or AnomalyPolicyEngine(cooldown_minutes=COOLDOWN_MINUTES)
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
    ) -> list[dict[str, object]]:
        context = await self._repo.load_fast_detection_context(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            lookback=FAST_PATH_LOOKBACK,
        )
        if context is None:
            return []
        created_payloads = await self._run_detection_pass(
            context,
            detectors=self._fast_detectors,
            source_pipeline=ANOMALY_SOURCE_FAST_PATH,
            extra_payload={"source": source or ANOMALY_SOURCE_FAST_PATH},
        )
        return created_payloads

    async def scan_sector_synchrony(
        self,
        *,
        trigger_coin_id: int,
        timeframe: int,
        timestamp: datetime,
        trigger_anomaly_id: int | None = None,
    ) -> dict[str, object]:
        context = await self._repo.load_sector_detection_context(
            coin_id=trigger_coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            lookback=SECTOR_SCAN_LOOKBACK,
        )
        if context is None:
            return {"status": "skipped", "reason": "context_unavailable"}
        created = await self._run_detection_pass(
            context,
            detectors=(self._sector_detector,),
            source_pipeline=ANOMALY_SOURCE_SECTOR_SCAN,
            extra_payload={"trigger_anomaly_id": trigger_anomaly_id},
        )
        return {
            "status": "ok",
            "created": len(created),
            "items": created,
        }

    async def scan_market_structure(
        self,
        *,
        trigger_coin_id: int,
        timeframe: int,
        timestamp: datetime,
        trigger_anomaly_id: int | None = None,
    ) -> dict[str, object]:
        context = await self._repo.load_market_structure_detection_context(
            coin_id=trigger_coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            lookback=MARKET_STRUCTURE_LOOKBACK,
        )
        if context is None:
            return {"status": "skipped", "reason": "context_unavailable"}
        if not context.venue_snapshots:
            return {"status": "skipped", "reason": "market_structure_unavailable"}
        created = await self._run_detection_pass(
            context,
            detectors=self._market_structure_detectors,
            source_pipeline=ANOMALY_SOURCE_MARKET_STRUCTURE_SCAN,
            extra_payload={"trigger_anomaly_id": trigger_anomaly_id},
        )
        return {
            "status": "ok",
            "created": len(created),
            "items": created,
        }

    async def enrich_anomaly(self, anomaly_id: int) -> dict[str, object]:
        anomaly = await self._repo.get_anomaly(anomaly_id)
        if anomaly is None:
            return {"status": "error", "reason": "anomaly_not_found", "anomaly_id": anomaly_id}

        payload_json = dict(anomaly.payload_json or {})
        payload_context = dict(payload_json.get("context", {}))
        explainability = dict(payload_json.get("explainability", {}))
        portfolio_relevant = await self._repo.has_open_portfolio_position(int(anomaly.coin_id), int(anomaly.timeframe))
        sector_active_count = await self._repo.count_active_sector_anomalies(
            sector=anomaly.sector,
            timeframe=int(anomaly.timeframe),
        )
        market_wide = bool(payload_context.get("scope") == "sector" or sector_active_count > 1)

        payload_context.update(
            {
                "portfolio_relevant": portfolio_relevant,
                "market_wide": market_wide,
            }
        )
        explainability.update(
            {
                "portfolio_impact": (
                    "portfolio exposure present"
                    if portfolio_relevant
                    else "no open portfolio position for this instrument/timeframe"
                ),
                "market_scope": "market-wide" if market_wide else "isolated",
                "enriched_by": ANOMALY_SOURCE_ENRICHMENT,
            }
        )
        payload_json["context"] = payload_context
        payload_json["explainability"] = explainability
        await self._repo.touch_anomaly(
            anomaly,
            status=ANOMALY_STATUS_ACTIVE if anomaly.status == ANOMALY_STATUS_NEW else anomaly.status,
            payload_json=payload_json,
        )
        await self._session.commit()
        return {
            "status": "ok",
            "anomaly_id": int(anomaly.id),
            "portfolio_relevant": portfolio_relevant,
            "market_wide": market_wide,
        }

    async def _run_detection_pass(
        self,
        context: AnomalyDetectionContext,
        *,
        detectors: tuple[object, ...],
        source_pipeline: str,
        extra_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, object]]:
        created_anomalies = []
        changed = False
        for detector in detectors:
            finding = detector.detect(context)
            if finding is None:
                continue
            score, severity, confidence = self._scorer.score(finding)
            latest_anomaly = await self._repo.load_latest_open_anomaly(
                coin_id=context.coin_id,
                timeframe=context.timeframe,
                anomaly_type=finding.anomaly_type,
            )
            decision = self._policy_engine.evaluate(
                anomaly_type=finding.anomaly_type,
                score=score,
                detected_at=context.timestamp,
                market_regime=context.market_regime,
                latest_anomaly=latest_anomaly,
                confirmation_hits=finding.confirmation_hits,
                confirmation_target=finding.confirmation_target,
            )
            changed |= decision.action in {"create", "refresh", "transition"}
            if decision.action == "create":
                draft = self._build_draft(
                    context,
                    finding,
                    score=score,
                    severity=severity,
                    confidence=confidence,
                    status=decision.status or ANOMALY_STATUS_NEW,
                    source_pipeline=source_pipeline,
                    extra_payload=extra_payload,
                )
                created = await self._repo.create_anomaly(draft)
                created_anomalies.append((created, draft))
                continue

            if latest_anomaly is None:
                continue

            if decision.action == "refresh":
                await self._repo.touch_anomaly(
                    latest_anomaly,
                    status=decision.status or latest_anomaly.status,
                    score=score,
                    confidence=confidence,
                    summary=finding.summary,
                    payload_json=self._draft_payload(context, finding, source_pipeline, extra_payload=extra_payload),
                    last_confirmed_at=context.timestamp,
                )
                continue

            if decision.action == "transition":
                await self._repo.touch_anomaly(
                    latest_anomaly,
                    status=decision.status,
                    score=score,
                    confidence=confidence,
                    summary=finding.summary,
                    payload_json=self._draft_payload(context, finding, source_pipeline, extra_payload=extra_payload),
                    resolved_at=context.timestamp if decision.status == ANOMALY_STATUS_RESOLVED else None,
                )

        if changed:
            await self._session.commit()

        published_payloads: list[dict[str, object]] = []
        for anomaly, draft in created_anomalies:
            # NOTE:
            # The stream publisher exposes a synchronous enqueue API on purpose.
            # Redis writes are drained on a dedicated background thread, so this
            # async service does not block on network I/O in the event loop here.
            payload = draft.to_event_payload(int(anomaly.id))
            publish_event(ANOMALY_EVENT_TYPE, payload)
            published_payloads.append(payload)
        return published_payloads

    def _build_draft(
        self,
        context: AnomalyDetectionContext,
        finding: DetectorFinding,
        *,
        score: float,
        severity: str,
        confidence: float,
        status: str,
        source_pipeline: str,
        extra_payload: dict[str, Any] | None,
    ) -> AnomalyDraft:
        return AnomalyDraft(
            coin_id=context.coin_id,
            symbol=context.symbol,
            timeframe=context.timeframe,
            anomaly_type=finding.anomaly_type,
            severity=severity,
            confidence=confidence,
            score=score,
            status=status,
            detected_at=context.timestamp,
            window_start=context.window_start,
            window_end=context.window_end,
            market_regime=context.market_regime,
            sector=context.sector,
            summary=finding.summary,
            payload_json=self._draft_payload(
                context,
                finding,
                source_pipeline,
                extra_payload=extra_payload,
            ),
            cooldown_until=self._policy_engine.cooldown_until(finding.anomaly_type, context.timestamp),
        )

    def _draft_payload(
        self,
        context: AnomalyDetectionContext,
        finding: DetectorFinding,
        source_pipeline: str,
        *,
        extra_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = {
            "metrics": dict(finding.metrics),
            "components": {name: float(value) for name, value in finding.component_scores.items()},
            "context": {
                "sector": context.sector,
                "market_regime": context.market_regime,
                "relative_to_btc": finding.explainability.get("relative_to_btc"),
                "scope": finding.scope,
                "isolated_move": finding.isolated,
                "portfolio_relevant": context.portfolio_relevant,
            },
            "explainability": {
                "what_happened": finding.explainability.get("what_happened"),
                "unusualness": finding.explainability.get("unusualness"),
                "relative_to": finding.explainability.get("relative_to"),
                "market_wide": finding.explainability.get("market_wide"),
                "affected_symbols": list(finding.affected_symbols),
            },
            "source_pipeline": source_pipeline,
            "affected_symbols": list(finding.affected_symbols),
        }
        if extra_payload:
            payload.update(extra_payload)
        return payload
