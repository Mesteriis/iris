from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from src.apps.explanations.api.contracts import ExplanationJobAcceptedRead
from src.apps.explanations.api.deps import ExplanationJobDispatcherDep, ExplanationQueryDep
from src.apps.explanations.api.presenters import explanation_job_accepted_read
from src.apps.explanations.contracts import ExplainKind
from src.apps.explanations.language import resolve_effective_language

router = APIRouter(tags=["explanations:jobs"])


@router.post(
    "/signals/{signal_id}/jobs/run",
    response_model=ExplanationJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue signal explanation generation",
)
async def run_signal_explanation_job(
    signal_id: int,
    dispatcher: ExplanationJobDispatcherDep,
    service: ExplanationQueryDep,
    language: str | None = Query(default=None),
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> ExplanationJobAcceptedRead:
    if not await service.signal_exists(int(signal_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found.")
    effective_language = resolve_effective_language({"language": language})
    bundle = await service.build_signal_context(int(signal_id))
    assert bundle is not None
    dispatch_result = await dispatcher.dispatch_generation(
        explain_kind=ExplainKind.SIGNAL,
        subject_id=int(signal_id),
        language=effective_language,
        requested_provider=requested_provider,
        force=force,
    )
    return explanation_job_accepted_read(
        dispatch_result=dispatch_result,
        explain_kind=ExplainKind.SIGNAL,
        subject_id=int(signal_id),
        language=effective_language,
        symbol=bundle.symbol,
        timeframe=bundle.timeframe,
    )


@router.post(
    "/decisions/{decision_id}/jobs/run",
    response_model=ExplanationJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue decision explanation generation",
)
async def run_decision_explanation_job(
    decision_id: int,
    dispatcher: ExplanationJobDispatcherDep,
    service: ExplanationQueryDep,
    language: str | None = Query(default=None),
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> ExplanationJobAcceptedRead:
    if not await service.decision_exists(int(decision_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found.")
    effective_language = resolve_effective_language({"language": language})
    bundle = await service.build_decision_context(int(decision_id))
    assert bundle is not None
    dispatch_result = await dispatcher.dispatch_generation(
        explain_kind=ExplainKind.DECISION,
        subject_id=int(decision_id),
        language=effective_language,
        requested_provider=requested_provider,
        force=force,
    )
    return explanation_job_accepted_read(
        dispatch_result=dispatch_result,
        explain_kind=ExplainKind.DECISION,
        subject_id=int(decision_id),
        language=effective_language,
        symbol=bundle.symbol,
        timeframe=bundle.timeframe,
    )


__all__ = ["router"]
