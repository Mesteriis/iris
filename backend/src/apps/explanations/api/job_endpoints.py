from __future__ import annotations

from fastapi import APIRouter, Query, status

from src.apps.explanations.api.contracts import ExplanationJobAcceptedRead
from src.apps.explanations.api.deps import ExplanationJobDispatcherDep, ExplanationQueryDep
from src.apps.explanations.api.errors import decision_not_found_error, signal_not_found_error
from src.apps.explanations.api.presenters import explanation_job_accepted_read
from src.apps.explanations.contracts import ExplainKind
from src.core.http.deps import RequestLocaleDep

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
    request_locale: RequestLocaleDep,
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> ExplanationJobAcceptedRead:
    if not await service.signal_exists(int(signal_id)):
        raise signal_not_found_error(locale=request_locale)
    bundle = await service.build_signal_context(int(signal_id))
    assert bundle is not None
    dispatch_result = await dispatcher.dispatch_generation(
        explain_kind=ExplainKind.SIGNAL,
        subject_id=int(signal_id),
        requested_provider=requested_provider,
        force=force,
    )
    return explanation_job_accepted_read(
        dispatch_result=dispatch_result,
        explain_kind=ExplainKind.SIGNAL,
        subject_id=int(signal_id),
        rendered_locale=request_locale,
        symbol=bundle.symbol,
        timeframe=bundle.timeframe,
        locale=request_locale,
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
    request_locale: RequestLocaleDep,
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> ExplanationJobAcceptedRead:
    if not await service.decision_exists(int(decision_id)):
        raise decision_not_found_error(locale=request_locale)
    bundle = await service.build_decision_context(int(decision_id))
    assert bundle is not None
    dispatch_result = await dispatcher.dispatch_generation(
        explain_kind=ExplainKind.DECISION,
        subject_id=int(decision_id),
        requested_provider=requested_provider,
        force=force,
    )
    return explanation_job_accepted_read(
        dispatch_result=dispatch_result,
        explain_kind=ExplainKind.DECISION,
        subject_id=int(decision_id),
        rendered_locale=request_locale,
        symbol=bundle.symbol,
        timeframe=bundle.timeframe,
        locale=request_locale,
    )


__all__ = ["router"]
