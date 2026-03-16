from datetime import datetime
from typing import Any

from src.apps.anomalies.constants import (
    ANOMALY_EVENT_TYPE,
    ANOMALY_STATUS_COOLING,
    ANOMALY_STATUS_NEW,
    ANOMALY_STATUS_RESOLVED,
)
from src.apps.anomalies.contracts import AnomalyDetectionContext, AnomalyDraft, DetectorFinding
from src.apps.anomalies.engines import build_anomaly_payload
from src.apps.anomalies.policies import AnomalyPolicyEngine
from src.apps.anomalies.repos import AnomalyRepo
from src.apps.anomalies.results import AnomalyDetectionBatchResult
from src.apps.anomalies.scoring import AnomalyScorer
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.publisher import publish_event


class AnomalyDetectionRunner:
    def __init__(
        self,
        *,
        uow: BaseAsyncUnitOfWork,
        repo: AnomalyRepo,
        scorer: AnomalyScorer,
        policy_engine: AnomalyPolicyEngine,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._scorer = scorer
        self._policy_engine = policy_engine

    async def run(
        self,
        context: AnomalyDetectionContext,
        *,
        detectors: tuple[object, ...],
        source_pipeline: str,
        extra_payload: dict[str, Any] | None = None,
    ) -> AnomalyDetectionBatchResult:
        created_anomalies: list[tuple[object, AnomalyDraft]] = []
        for detector in detectors:
            finding = detector.detect(context)
            if finding is None:
                continue
            score, severity, confidence = self._scorer.score(finding)
            latest_anomaly = await self._repo.get_latest_open_for_update(
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
                    payload_json=build_anomaly_payload(
                        context,
                        finding,
                        source_pipeline,
                        extra_payload=extra_payload,
                    ),
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
                    payload_json=build_anomaly_payload(
                        context,
                        finding,
                        source_pipeline,
                        extra_payload=extra_payload,
                    ),
                    resolved_at=context.timestamp if decision.status == ANOMALY_STATUS_RESOLVED else None,
                )

        items = tuple(self._schedule_publication(anomaly_id=int(anomaly.id), draft=draft) for anomaly, draft in created_anomalies)
        return AnomalyDetectionBatchResult(
            status="ok",
            created=len(items),
            items=items,
        )

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
            payload_json=build_anomaly_payload(
                context,
                finding,
                source_pipeline,
                extra_payload=extra_payload,
            ),
            cooldown_until=self._policy_engine.cooldown_until(finding.anomaly_type, context.timestamp),
        )

    def _schedule_publication(self, *, anomaly_id: int, draft: AnomalyDraft) -> dict[str, Any]:
        payload = draft.to_event_payload(anomaly_id)
        self._uow.add_after_commit_action(
            lambda payload=dict(payload): publish_event(ANOMALY_EVENT_TYPE, payload)
        )
        return payload


__all__ = ["AnomalyDetectionRunner"]
