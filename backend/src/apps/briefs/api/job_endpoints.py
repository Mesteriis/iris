from __future__ import annotations

from fastapi import APIRouter, Query, status

from src.apps.briefs.api.contracts import BriefJobAcceptedRead
from src.apps.briefs.api.deps import BriefJobDispatcherDep, BriefQueryDep
from src.apps.briefs.api.errors import symbol_not_found_error
from src.apps.briefs.api.presenters import brief_job_accepted_read
from src.apps.briefs.contracts import BriefKind, build_scope_key
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["briefs:jobs"])


@router.post(
    "/market/jobs/run",
    response_model=BriefJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue market brief generation",
)
async def run_market_brief_job(
    dispatcher: BriefJobDispatcherDep,
    request_locale: RequestLocaleDep,
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> BriefJobAcceptedRead:
    dispatch_result = await dispatcher.dispatch_generation(
        brief_kind=BriefKind.MARKET,
        force=force,
        requested_provider=requested_provider,
    )
    return brief_job_accepted_read(
        dispatch_result=dispatch_result,
        brief_kind=BriefKind.MARKET,
        scope_key=build_scope_key(BriefKind.MARKET),
        rendered_locale=request_locale,
        locale=request_locale,
    )


@router.post(
    "/portfolio/jobs/run",
    response_model=BriefJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue portfolio brief generation",
)
async def run_portfolio_brief_job(
    dispatcher: BriefJobDispatcherDep,
    request_locale: RequestLocaleDep,
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> BriefJobAcceptedRead:
    dispatch_result = await dispatcher.dispatch_generation(
        brief_kind=BriefKind.PORTFOLIO,
        force=force,
        requested_provider=requested_provider,
    )
    return brief_job_accepted_read(
        dispatch_result=dispatch_result,
        brief_kind=BriefKind.PORTFOLIO,
        scope_key=build_scope_key(BriefKind.PORTFOLIO),
        rendered_locale=request_locale,
        locale=request_locale,
    )


@router.post(
    "/symbols/{symbol}/jobs/run",
    response_model=BriefJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue symbol brief generation",
)
async def run_symbol_brief_job(
    symbol: str,
    dispatcher: BriefJobDispatcherDep,
    service: BriefQueryDep,
    request_locale: RequestLocaleDep,
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> BriefJobAcceptedRead:
    normalized_symbol = str(symbol).strip().upper()
    if not await service.symbol_exists(normalized_symbol):
        raise symbol_not_found_error(locale=request_locale)
    dispatch_result = await dispatcher.dispatch_generation(
        brief_kind=BriefKind.SYMBOL,
        symbol=normalized_symbol,
        force=force,
        requested_provider=requested_provider,
    )
    return brief_job_accepted_read(
        dispatch_result=dispatch_result,
        brief_kind=BriefKind.SYMBOL,
        scope_key=build_scope_key(BriefKind.SYMBOL, symbol=normalized_symbol),
        rendered_locale=request_locale,
        symbol=normalized_symbol,
        locale=request_locale,
    )


__all__ = ["router"]
