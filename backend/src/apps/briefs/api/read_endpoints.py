from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from src.apps.briefs.api.contracts import BriefRead
from src.apps.briefs.api.deps import BriefQueryDep
from src.apps.briefs.api.presenters import brief_read
from src.apps.briefs.contracts import BriefKind, build_scope_key
from src.apps.briefs.language import resolve_effective_language
from src.core.http.cache import PRIVATE_NEAR_REALTIME_CACHE, apply_conditional_cache, cache_not_modified_responses

router = APIRouter(tags=["briefs:read"])


@router.get(
    "/market",
    response_model=BriefRead,
    summary="Read stored market brief",
    responses=cache_not_modified_responses(),
)
async def read_market_brief(
    request: Request,
    response: Response,
    service: BriefQueryDep,
    language: str | None = Query(default=None),
) -> BriefRead | Response:
    return await _read_brief(
        request=request,
        response=response,
        service=service,
        brief_kind=BriefKind.MARKET,
        scope_key=build_scope_key(BriefKind.MARKET),
        language=resolve_effective_language({"language": language}),
    )


@router.get(
    "/portfolio",
    response_model=BriefRead,
    summary="Read stored portfolio brief",
    responses=cache_not_modified_responses(),
)
async def read_portfolio_brief(
    request: Request,
    response: Response,
    service: BriefQueryDep,
    language: str | None = Query(default=None),
) -> BriefRead | Response:
    return await _read_brief(
        request=request,
        response=response,
        service=service,
        brief_kind=BriefKind.PORTFOLIO,
        scope_key=build_scope_key(BriefKind.PORTFOLIO),
        language=resolve_effective_language({"language": language}),
    )


@router.get(
    "/symbols/{symbol}",
    response_model=BriefRead,
    summary="Read stored symbol brief",
    responses=cache_not_modified_responses(),
)
async def read_symbol_brief(
    symbol: str,
    request: Request,
    response: Response,
    service: BriefQueryDep,
    language: str | None = Query(default=None),
) -> BriefRead | Response:
    normalized_symbol = str(symbol).strip().upper()
    return await _read_brief(
        request=request,
        response=response,
        service=service,
        brief_kind=BriefKind.SYMBOL,
        scope_key=build_scope_key(BriefKind.SYMBOL, symbol=normalized_symbol),
        language=resolve_effective_language({"language": language}),
    )


async def _read_brief(
    *,
    request: Request,
    response: Response,
    service: BriefQueryDep,
    brief_kind: BriefKind,
    scope_key: str,
    language: str,
) -> BriefRead | Response:
    item = await service.get_brief(brief_kind=brief_kind, scope_key=scope_key, language=language)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found.")
    payload = brief_read(item)
    if not_modified := apply_conditional_cache(
        request=request,
        response=response,
        payload=payload,
        policy=PRIVATE_NEAR_REALTIME_CACHE,
        generated_at=payload.generated_at,
        staleness_ms=payload.staleness_ms,
    ):
        return not_modified
    return payload


__all__ = ["router"]
