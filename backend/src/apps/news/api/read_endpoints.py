from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.news.api.contracts import NewsItemRead, NewsPluginRead, NewsSourceRead
from src.apps.news.api.deps import NewsQueryDep
from src.apps.news.api.presenters import news_item_read, news_plugin_read, news_source_read

router = APIRouter(tags=["news:read"])


@router.get("/plugins", response_model=list[NewsPluginRead], summary="List news plugins")
async def read_news_plugins(service: NewsQueryDep) -> list[NewsPluginRead]:
    return [news_plugin_read(item) for item in await service.list_plugins()]


@router.get("/sources", response_model=list[NewsSourceRead], summary="List news sources")
async def read_news_sources(service: NewsQueryDep) -> list[NewsSourceRead]:
    return [news_source_read(item) for item in await service.list_sources()]


@router.get("/items", response_model=list[NewsItemRead], summary="List news items")
async def read_news_items(
    service: NewsQueryDep,
    source_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[NewsItemRead]:
    items = await service.list_items(source_id=source_id, limit=limit)
    return [news_item_read(item) for item in items]
