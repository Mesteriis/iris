from __future__ import annotations

from fastapi import APIRouter, Request, Response

from src.apps.briefs.api.contracts import BriefRead
from src.apps.briefs.api.deps import BriefQueryDep
from src.apps.briefs.api.errors import brief_not_found_error
from src.apps.briefs.api.presenters import brief_read
from src.apps.briefs.contracts import BriefKind, build_scope_key
from src.core.http.cache import PRIVATE_NEAR_REALTIME_CACHE, apply_conditional_cache, cache_not_modified_responses
from src.core.http.deps import RequestLocaleDep

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
    request_locale: RequestLocaleDep,
) -> BriefRead | Response:
    return await _read_brief(
        request=request,
        response=response,
        service=service,
        brief_kind=BriefKind.MARKET,
        scope_key=build_scope_key(BriefKind.MARKET),
        locale=request_locale,
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
    request_locale: RequestLocaleDep,
) -> BriefRead | Response:
    return await _read_brief(
        request=request,
        response=response,
        service=service,
        brief_kind=BriefKind.PORTFOLIO,
        scope_key=build_scope_key(BriefKind.PORTFOLIO),
        locale=request_locale,
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
    request_locale: RequestLocaleDep,
) -> BriefRead | Response:
    normalized_symbol = str(symbol).strip().upper()
    return await _read_brief(
        request=request,
        response=response,
        service=service,
        brief_kind=BriefKind.SYMBOL,
        scope_key=build_scope_key(BriefKind.SYMBOL, symbol=normalized_symbol),
        locale=request_locale,
    )


async def _read_brief(
    *,
    request: Request,
    response: Response,
    service: BriefQueryDep,
    brief_kind: BriefKind,
    scope_key: str,
    locale: str,
) -> BriefRead | Response:
    item = await service.get_brief(brief_kind=brief_kind, scope_key=scope_key)
    if item is None:
        raise brief_not_found_error(locale=locale)
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
