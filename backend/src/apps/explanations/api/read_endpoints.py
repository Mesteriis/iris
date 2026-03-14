from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from src.apps.explanations.api.contracts import ExplanationRead
from src.apps.explanations.api.deps import ExplanationQueryDep
from src.apps.explanations.api.presenters import explanation_read
from src.apps.explanations.contracts import ExplainKind
from src.apps.explanations.language import resolve_effective_language
from src.core.http.cache import PUBLIC_NEAR_REALTIME_CACHE, apply_conditional_cache, cache_not_modified_responses

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
    language: str | None = Query(default=None),
) -> ExplanationRead | Response:
    return await _read_explanation(
        request=request,
        response=response,
        service=service,
        explain_kind=ExplainKind.SIGNAL,
        subject_id=int(signal_id),
        language=resolve_effective_language({"language": language}),
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
    language: str | None = Query(default=None),
) -> ExplanationRead | Response:
    return await _read_explanation(
        request=request,
        response=response,
        service=service,
        explain_kind=ExplainKind.DECISION,
        subject_id=int(decision_id),
        language=resolve_effective_language({"language": language}),
    )


async def _read_explanation(
    *,
    request: Request,
    response: Response,
    service: ExplanationQueryDep,
    explain_kind: ExplainKind,
    subject_id: int,
    language: str,
) -> ExplanationRead | Response:
    item = await service.get_explanation(
        explain_kind=explain_kind,
        subject_id=int(subject_id),
        language=language,
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Explanation not found.")
    payload = explanation_read(item)
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
