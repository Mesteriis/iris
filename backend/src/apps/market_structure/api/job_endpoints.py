from __future__ import annotations

from fastapi import APIRouter, Query, status

from src.apps.market_structure.api.contracts import (
    MarketStructureHealthJobAcceptedRead,
    MarketStructureSourceJobAcceptedRead,
)
from src.apps.market_structure.api.deps import (
    MarketStructureJobDispatcherDep,
    MarketStructureQueryDep,
)
from src.apps.market_structure.api.errors import market_structure_error_responses, market_structure_source_not_found_error
from src.apps.market_structure.api.presenters import (
    market_structure_health_job_accepted_read,
    market_structure_source_job_accepted_read,
)

router = APIRouter(tags=["market-structure:jobs"])


@router.post(
    "/sources/{source_id}/jobs/run",
    response_model=MarketStructureSourceJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue market structure source poll job",
    responses=market_structure_error_responses(404),
)
async def run_market_structure_source_job(
    source_id: int,
    query_service: MarketStructureQueryDep,
    dispatcher: MarketStructureJobDispatcherDep,
    limit: int = Query(default=1, ge=1, le=10),
) -> MarketStructureSourceJobAcceptedRead:
    if await query_service.get_source_read_by_id(source_id) is None:
        raise market_structure_source_not_found_error(source_id)
    dispatch_result = await dispatcher.dispatch_source_poll(source_id=int(source_id), limit=int(limit))
    return market_structure_source_job_accepted_read(
        dispatch_result=dispatch_result,
        source_id=source_id,
        limit=limit,
    )


@router.post(
    "/health/jobs/run",
    response_model=MarketStructureHealthJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue market structure health refresh job",
)
async def run_market_structure_health_job(
    dispatcher: MarketStructureJobDispatcherDep,
) -> MarketStructureHealthJobAcceptedRead:
    dispatch_result = await dispatcher.dispatch_health_refresh()
    return market_structure_health_job_accepted_read(dispatch_result=dispatch_result)
