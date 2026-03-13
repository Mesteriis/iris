from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.apps.market_data.models import Coin
from src.apps.news.models import NewsItem, NewsItemLink
from src.apps.news.query_services import NewsQueryService
from src.apps.news.schemas import NewsSourceCreate
from src.apps.news.services import NewsService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_news_query_returns_immutable_source_read_models(async_db_session) -> None:
    async with SessionUnitOfWork(async_db_session) as uow:
        created = await NewsService(uow).create_source(
            NewsSourceCreate(
                plugin_name="x",
                display_name="Macro Feed",
                credentials={"bearer_token": "secret-token"},
                settings={"user_id": "42"},
            )
        )
        items = await NewsQueryService(uow.session).list_sources()

    source = next(item for item in items if item.id == created.id)
    with pytest.raises(FrozenInstanceError):
        source.display_name = "changed"
    with pytest.raises(TypeError):
        source.settings["user_id"] = "84"


@pytest.mark.asyncio
async def test_news_query_returns_immutable_item_read_models(async_db_session, seeded_market) -> None:
    async with SessionUnitOfWork(async_db_session) as uow:
        created = await NewsService(uow).create_source(
            NewsSourceCreate(
                plugin_name="x",
                display_name="Desk Wire",
                credentials={"bearer_token": "secret-token"},
                settings={"user_id": "7"},
            )
        )
        await uow.commit()

    coin_id = int((await async_db_session.execute(select(Coin.id).order_by(Coin.id.asc()).limit(1))).scalar_one())
    async_db_session.add(
        NewsItem(
            source_id=created.id,
            plugin_name="x",
            external_id="tweet-immutable",
            published_at=datetime(2026, 3, 12, 13, 0, tzinfo=timezone.utc),
            author_handle="macrodesk",
            channel_name="Desk Wire",
            content_text="Watching $BTC react to ETF flow",
            url="https://x.com/i/web/status/immutable",
            symbol_hints=["BTC"],
            payload_json={"kind": "tweet"},
            normalized_payload_json={"detected_symbols": ["BTC"]},
            relevance_score=0.85,
        )
    )
    await async_db_session.commit()
    item = (
        await async_db_session.execute(select(NewsItem).where(NewsItem.external_id == "tweet-immutable").limit(1))
    ).scalar_one()
    async_db_session.add(
        NewsItemLink(
            news_item_id=int(item.id),
            coin_id=coin_id,
            coin_symbol="BTCUSD",
            matched_symbol="BTC",
            link_type="symbol",
            confidence=0.9,
        )
    )
    await async_db_session.commit()

    items = await NewsQueryService(async_db_session).list_items(source_id=created.id, limit=10)

    assert len(items) == 1
    with pytest.raises(FrozenInstanceError):
        items[0].external_id = "changed"
    with pytest.raises(TypeError):
        items[0].normalized_payload_json["detected_symbols"] = []
    with pytest.raises(FrozenInstanceError):
        items[0].links[0].confidence = 0.1


@pytest.mark.asyncio
async def test_news_persistence_logs_cover_query_and_uow(async_db_session, monkeypatch) -> None:
    events: list[str] = []

    def _debug(message: str, *args, **kwargs) -> None:
        del args, kwargs
        events.append(message)

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "debug", _debug)
    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    async with SessionUnitOfWork(async_db_session) as uow:
        await NewsService(uow).create_source(
            NewsSourceCreate(
                plugin_name="x",
                display_name="Log Feed",
                credentials={"bearer_token": "secret-token"},
                settings={"user_id": "9"},
            )
        )
        items = await NewsQueryService(uow.session).list_sources()
        await uow.commit()

    assert items
    assert "uow.begin" in events
    assert "repo.add_news_source" in events
    assert "query.list_news_sources" in events
    assert "uow.commit" in events
