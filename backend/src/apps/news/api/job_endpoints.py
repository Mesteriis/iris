from __future__ import annotations

from fastapi import APIRouter, Query, status

from src.apps.news.api.contracts import NewsSourceJobAcceptedRead
from src.apps.news.api.deps import NewsJobDispatcherDep, NewsQueryDep
from src.apps.news.api.errors import news_error_responses, news_source_not_found_error
from src.apps.news.api.presenters import news_source_job_accepted_read

router = APIRouter(tags=["news:jobs"])


@router.post(
    "/sources/{source_id}/jobs/run",
    response_model=NewsSourceJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue news source poll job",
    responses=news_error_responses(404),
)
async def run_news_source_job(
    source_id: int,
    query_service: NewsQueryDep,
    dispatcher: NewsJobDispatcherDep,
    limit: int = Query(default=50, ge=1, le=100),
) -> NewsSourceJobAcceptedRead:
    if await query_service.get_source_read_by_id(source_id) is None:
        raise news_source_not_found_error(source_id)
    operation = await dispatcher.dispatch_source_poll(source_id=int(source_id), limit=int(limit))
    return news_source_job_accepted_read(operation=operation, source_id=source_id, limit=limit)
