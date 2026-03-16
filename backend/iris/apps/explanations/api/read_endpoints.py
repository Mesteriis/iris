from fastapi import APIRouter, Request, Response

from iris.apps.explanations.api.contracts import ExplanationRead
from iris.apps.explanations.api.deps import ExplanationQueryDep
from iris.apps.explanations.api.errors import explanation_not_found_error
from iris.apps.explanations.api.presenters import explanation_read
from iris.apps.explanations.contracts import ExplainKind
from iris.core.http.cache import PUBLIC_NEAR_REALTIME_CACHE, apply_conditional_cache, cache_not_modified_responses
from iris.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["explanations:read"])


@router.get(
    "/signals/{signal_id}",
    response_model=ExplanationRead,
    summary="Read stored signal explanation",
    responses=cache_not_modified_responses(),
)
async def read_signal_explanation(
    signal_id: int,
    request: Request,
    response: Response,
    service: ExplanationQueryDep,
    request_locale: RequestLocaleDep,
) -> ExplanationRead | Response:
    return await _read_explanation(
        request=request,
        response=response,
        service=service,
        explain_kind=ExplainKind.SIGNAL,
        subject_id=int(signal_id),
        locale=request_locale,
    )


@router.get(
    "/decisions/{decision_id}",
    response_model=ExplanationRead,
    summary="Read stored decision explanation",
    responses=cache_not_modified_responses(),
)
async def read_decision_explanation(
    decision_id: int,
    request: Request,
    response: Response,
    service: ExplanationQueryDep,
    request_locale: RequestLocaleDep,
) -> ExplanationRead | Response:
    return await _read_explanation(
        request=request,
        response=response,
        service=service,
        explain_kind=ExplainKind.DECISION,
        subject_id=int(decision_id),
        locale=request_locale,
    )


async def _read_explanation(
    *,
    request: Request,
    response: Response,
    service: ExplanationQueryDep,
    explain_kind: ExplainKind,
    subject_id: int,
    locale: str,
) -> ExplanationRead | Response:
    item = await service.get_explanation(
        explain_kind=explain_kind,
        subject_id=int(subject_id),
    )
    if item is None:
        raise explanation_not_found_error(locale=locale)
    payload = explanation_read(item, locale=locale)
    if not_modified := apply_conditional_cache(
        request=request,
        response=response,
        payload=payload,
        policy=PUBLIC_NEAR_REALTIME_CACHE,
        generated_at=payload.generated_at,
        staleness_ms=payload.staleness_ms,
    ):
        return not_modified
    return payload


__all__ = ["router"]
