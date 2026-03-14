from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from src.apps.briefs.api.contracts import BriefJobAcceptedRead
from src.apps.briefs.api.deps import BriefJobDispatcherDep, BriefQueryDep
from src.apps.briefs.api.presenters import brief_job_accepted_read
from src.apps.briefs.contracts import BriefKind, build_scope_key
from src.apps.briefs.language import resolve_effective_language

router = APIRouter(tags=["briefs:jobs"])


@router.post(
    "/market/jobs/run",
    response_model=BriefJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue market brief generation",
)
async def run_market_brief_job(
    dispatcher: BriefJobDispatcherDep,
    language: str | None = Query(default=None),
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> BriefJobAcceptedRead:
    effective_language = resolve_effective_language({"language": language})
    dispatch_result = await dispatcher.dispatch_generation(
        brief_kind=BriefKind.MARKET,
        language=effective_language,
        force=force,
        requested_provider=requested_provider,
    )
    return brief_job_accepted_read(
        dispatch_result=dispatch_result,
        brief_kind=BriefKind.MARKET,
        scope_key=build_scope_key(BriefKind.MARKET),
        language=effective_language,
    )


@router.post(
    "/portfolio/jobs/run",
    response_model=BriefJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue portfolio brief generation",
)
async def run_portfolio_brief_job(
    dispatcher: BriefJobDispatcherDep,
    language: str | None = Query(default=None),
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> BriefJobAcceptedRead:
    effective_language = resolve_effective_language({"language": language})
    dispatch_result = await dispatcher.dispatch_generation(
        brief_kind=BriefKind.PORTFOLIO,
        language=effective_language,
        force=force,
        requested_provider=requested_provider,
    )
    return brief_job_accepted_read(
        dispatch_result=dispatch_result,
        brief_kind=BriefKind.PORTFOLIO,
        scope_key=build_scope_key(BriefKind.PORTFOLIO),
        language=effective_language,
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
    language: str | None = Query(default=None),
    force: bool = Query(default=False),
    requested_provider: str | None = Query(default=None),
) -> BriefJobAcceptedRead:
    normalized_symbol = str(symbol).strip().upper()
    if not await service.symbol_exists(normalized_symbol):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Symbol not found.")
    effective_language = resolve_effective_language({"language": language})
    dispatch_result = await dispatcher.dispatch_generation(
        brief_kind=BriefKind.SYMBOL,
        symbol=normalized_symbol,
        language=effective_language,
        force=force,
        requested_provider=requested_provider,
    )
    return brief_job_accepted_read(
        dispatch_result=dispatch_result,
        brief_kind=BriefKind.SYMBOL,
        scope_key=build_scope_key(BriefKind.SYMBOL, symbol=normalized_symbol),
        language=effective_language,
        symbol=normalized_symbol,
    )


__all__ = ["router"]
