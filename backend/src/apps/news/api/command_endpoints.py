from __future__ import annotations

from fastapi import APIRouter, status

from src.apps.news.api.contracts import NewsSourceCreate, NewsSourceRead, NewsSourceUpdate
from src.apps.news.api.deps import NewsCommandDep
from src.apps.news.api.errors import NewsSourceNotFoundError, news_error_responses, news_error_to_http
from src.apps.news.api.presenters import news_source_read
from src.core.http.command_executor import execute_command, execute_command_no_content
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["news:commands"])


@router.post(
    "/sources",
    response_model=NewsSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a news source",
    responses=news_error_responses(400),
)
async def create_news_source(
    payload: NewsSourceCreate,
    commands: NewsCommandDep,
    request_locale: RequestLocaleDep,
) -> NewsSourceRead:
    return await execute_command(
        action=lambda: commands.service.create_source(payload),
        uow=commands.uow,
        presenter=news_source_read,
        translate_error=lambda exc: news_error_to_http(exc, locale=request_locale),
    )


@router.patch(
    "/sources/{source_id}",
    response_model=NewsSourceRead,
    summary="Update a news source",
    responses=news_error_responses(400, 404),
)
async def patch_news_source(
    source_id: int,
    payload: NewsSourceUpdate,
    commands: NewsCommandDep,
    request_locale: RequestLocaleDep,
) -> NewsSourceRead:
    async def action() -> NewsSourceRead:
        updated = await commands.service.update_source(source_id, payload)
        if updated is None:
            raise NewsSourceNotFoundError(source_id)
        return updated

    return await execute_command(
        action=action,
        uow=commands.uow,
        presenter=news_source_read,
        translate_error=lambda exc: news_error_to_http(exc, locale=request_locale),
    )


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a news source",
    responses=news_error_responses(404),
)
async def delete_news_source(
    source_id: int,
    commands: NewsCommandDep,
    request_locale: RequestLocaleDep,
) -> None:
    async def action() -> object:
        deleted = await commands.service.delete_source(source_id)
        if not deleted:
            raise NewsSourceNotFoundError(source_id)
        return {"deleted": True}

    await execute_command_no_content(
        action=action,
        uow=commands.uow,
        translate_error=lambda exc: news_error_to_http(exc, locale=request_locale),
    )
