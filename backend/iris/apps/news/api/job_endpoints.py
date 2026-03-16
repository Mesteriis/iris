from fastapi import APIRouter, Query, status

from iris.apps.news.api.contracts import NewsSourceJobAcceptedRead
from iris.apps.news.api.deps import NewsJobDispatcherDep, NewsQueryDep
from iris.apps.news.api.errors import news_error_responses, news_source_not_found_error
from iris.apps.news.api.presenters import news_source_job_accepted_read
from iris.core.http.deps import RequestLocaleDep

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
    request_locale: RequestLocaleDep,
    limit: int = Query(default=50, ge=1, le=100),
) -> NewsSourceJobAcceptedRead:
    if await query_service.get_source_read_by_id(source_id) is None:
        raise news_source_not_found_error(locale=request_locale)
    dispatch_result = await dispatcher.dispatch_source_poll(source_id=int(source_id), limit=int(limit))
    return news_source_job_accepted_read(dispatch_result=dispatch_result, source_id=source_id, limit=limit)
