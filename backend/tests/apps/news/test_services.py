from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
import src.apps.news.plugins as news_plugins
from sqlalchemy import select
from src.apps.news.api.onboarding_wizard import telegram_wizard_spec
from src.apps.news.exceptions import InvalidNewsSourceConfigurationError, UnsupportedNewsPluginError
from src.apps.news.models import NewsItem, NewsSource
from src.apps.news.plugins import (
    FetchedNewsItem,
    NewsFetchResult,
    NewsPluginDescriptor,
    NewsSourcePlugin,
    register_news_plugin,
)
from src.apps.news.schemas import (
    NewsSourceCreate,
    NewsSourceUpdate,
    TelegramBulkSubscribeRequest,
    TelegramDialogSelection,
    TelegramDialogsRequest,
    TelegramSessionCodeRequest,
    TelegramSessionConfirmRequest,
    TelegramSourceFromDialogCreate,
)
from src.apps.news.services import NewsService, TelegramSessionOnboardingService, TelegramSourceProvisioningService
from src.core.db.uow import SessionUnitOfWork
from src.core.http.router_policy import api_path


@dataclass(frozen=True, slots=True)
class _FixtureRow:
    external_id: str
    content_text: str
    author_handle: str


class FixtureNewsPlugin(NewsSourcePlugin):
    descriptor = NewsPluginDescriptor(
        name="fixture_news",
        display_name="Fixture News",
        description="Deterministic in-memory plugin used by tests.",
        auth_mode="fixture",
        supported=True,
        required_credentials=("token",),
        required_settings=("channel",),
    )

    _rows = (
        _FixtureRow(external_id="1", content_text="Watching $BTC breakout", author_handle="fixture-alpha"),
        _FixtureRow(external_id="2", content_text="Rotation into $ETH and $SOL", author_handle="fixture-beta"),
        _FixtureRow(external_id="3", content_text="Macro risk reset", author_handle="fixture-gamma"),
    )

    async def fetch_items(self, *, cursor: dict[str, Any], limit: int = 50) -> NewsFetchResult:
        after = int(cursor.get("after") or 0)
        selected = [row for row in self._rows if int(row.external_id) > after][:limit]
        base_time = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
        items = [
            FetchedNewsItem(
                external_id=row.external_id,
                published_at=base_time + timedelta(minutes=int(row.external_id)),
                author_handle=row.author_handle,
                channel_name=self.source.display_name,
                title=None,
                content_text=row.content_text,
                url=f"https://fixture.local/{row.external_id}",
                payload_json={"kind": "fixture", "external_id": row.external_id},
            )
            for row in selected
        ]
        next_cursor = dict(cursor)
        if items:
            next_cursor["after"] = max(int(item.external_id) for item in items)
        return NewsFetchResult(items=items, next_cursor=next_cursor)


@pytest.fixture
def isolated_news_registry() -> None:
    snapshot = dict(news_plugins._REGISTRY)
    try:
        yield
    finally:
        news_plugins._REGISTRY.clear()
        news_plugins._REGISTRY.update(snapshot)


@pytest.mark.asyncio
async def test_news_service_polls_persists_and_publishes(async_db_session, monkeypatch, isolated_news_registry) -> None:
    register_news_plugin("fixture_news", FixtureNewsPlugin)
    published: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        "src.apps.news.polling.publish_event",
        lambda event_name, payload: published.append((event_name, payload)),
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        service = NewsService(uow)
        source = await service.create_source(
            NewsSourceCreate(
                plugin_name="fixture_news",
                display_name="Fixture Feed",
                credentials={"token": "fixture-token"},
                settings={"channel": "feed"},
            )
        )
        first_poll = await service.poll_source(source_id=source.id, limit=2)
        second_poll = await service.poll_source(source_id=source.id, limit=2)
        await uow.commit()

    assert first_poll.status == "ok"
    assert first_poll.source_id == source.id
    assert first_poll.plugin_name == "fixture_news"
    assert first_poll.fetched == 2
    assert first_poll.created == 2
    assert first_poll.cursor == {"after": 2}
    assert second_poll.status == "ok"
    assert second_poll.source_id == source.id
    assert second_poll.plugin_name == "fixture_news"
    assert second_poll.fetched == 1
    assert second_poll.created == 1
    assert second_poll.cursor == {"after": 3}

    stored_source = await async_db_session.get(NewsSource, source.id)
    assert stored_source is not None
    assert stored_source.cursor_json == {"after": 3}
    assert stored_source.last_error is None
    assert stored_source.last_polled_at is not None

    items = (
        await async_db_session.execute(
            select(NewsItem)
            .where(NewsItem.source_id == source.id)
            .order_by(NewsItem.external_id.asc())
        )
    ).scalars().all()
    assert [item.external_id for item in items] == ["1", "2", "3"]
    assert items[0].symbol_hints == ["BTC"]
    assert items[1].symbol_hints == ["ETH", "SOL"]

    assert len(published) == 3
    assert all(event_name == "news_item_ingested" for event_name, _ in published)
    assert published[0][1]["source_id"] == source.id
    assert published[0][1]["external_id"] == "1"


@pytest.mark.asyncio
async def test_news_service_rejects_duplicate_and_unsupported_sources(async_db_session) -> None:
    async with SessionUnitOfWork(async_db_session) as uow:
        service = NewsService(uow)

        await service.create_source(
            NewsSourceCreate(
                plugin_name="x",
                display_name="Alpha Feed",
                credentials={"bearer_token": "x-token"},
                settings={"user_id": "123456"},
            )
        )
        await uow.commit()

        with pytest.raises(InvalidNewsSourceConfigurationError, match="already exists"):
            await service.create_source(
                NewsSourceCreate(
                    plugin_name="x",
                    display_name="Alpha Feed",
                    credentials={"bearer_token": "x-token"},
                    settings={"user_id": "123456"},
                )
            )

        with pytest.raises(UnsupportedNewsPluginError, match="developer API"):
            await service.create_source(
                NewsSourceCreate(
                    plugin_name="truth_social",
                    display_name="Truth Social Mirror",
                    credentials={},
                    settings={},
                )
            )


@pytest.mark.asyncio
async def test_news_service_updates_and_deletes_source(async_db_session) -> None:
    async with SessionUnitOfWork(async_db_session) as uow:
        service = NewsService(uow)

        created = await service.create_source(
            NewsSourceCreate(
                plugin_name="x",
                display_name="Desk One",
                credentials={"bearer_token": "token-a"},
                settings={"user_id": "101"},
            )
        )
        await uow.commit()

        updated = await service.update_source(
            created.id,
            NewsSourceUpdate(
                display_name="Desk Prime",
                enabled=False,
                credentials={"access_token": "token-b"},
                settings={"max_results": 25},
                reset_cursor=True,
                clear_error=True,
            ),
        )
        assert updated is not None
        assert updated.display_name == "Desk Prime"
        assert updated.enabled is False
        assert updated.status == "disabled"
        assert updated.settings == {"user_id": "101", "max_results": 25}
        assert updated.credential_fields_present == ["access_token", "bearer_token"]
        await uow.commit()

        stored = await async_db_session.get(NewsSource, created.id)
        assert stored is not None
        assert stored.cursor_json == {}
        assert stored.credentials_json["access_token"] == "token-b"

        assert await service.delete_source(created.id) is True
        await uow.commit()
        assert await service.delete_source(created.id) is False


@pytest.mark.asyncio
async def test_telegram_onboarding_service_returns_code_and_session(monkeypatch) -> None:
    class FakePasswordError(Exception):
        pass

    class FakeStringSession:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    class FakeSession:
        def save(self) -> str:
            return "session:telegram"

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            self.session = FakeSession()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def send_code_request(self, phone_number: str):
            return SimpleNamespace(phone_code_hash=f"hash:{phone_number}")

        async def sign_in(self, **kwargs):
            del kwargs
            return SimpleNamespace(id=77, username="iris_user", first_name="Iris", last_name="Operator")

        async def get_me(self):
            return SimpleNamespace(id=77, username="iris_user", first_name="Iris", last_name="Operator")

    monkeypatch.setattr(
        TelegramSessionOnboardingService,
        "_load_telethon",
        staticmethod(lambda: (FakeClient, FakeStringSession, FakePasswordError, SimpleNamespace())),
    )

    service = TelegramSessionOnboardingService()
    code_response = await service.request_code(
        TelegramSessionCodeRequest(
            api_id=1001,
            api_hash="hash",
            phone_number="+10000000000",
        )
    )
    assert code_response.status == "code_sent"
    assert code_response.phone_code_hash == "hash:+10000000000"

    confirm_response = await service.confirm_code(
        TelegramSessionConfirmRequest(
            api_id=1001,
            api_hash="hash",
            phone_number="+10000000000",
            phone_code_hash=code_response.phone_code_hash,
            code="12345",
        )
    )
    assert confirm_response.status == "authorized"
    assert confirm_response.session_string == "session:telegram"
    assert confirm_response.username == "iris_user"


@pytest.mark.asyncio
async def test_telegram_onboarding_service_lists_selectable_dialogs(monkeypatch) -> None:
    class FakePasswordError(Exception):
        pass

    class FakeStringSession:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    class FakeChannel:
        def __init__(self, entity_id: int, title: str, username: str | None, access_hash: int) -> None:
            self.id = entity_id
            self.title = title
            self.username = username
            self.access_hash = access_hash

    class FakeChat:
        def __init__(self, entity_id: int, title: str) -> None:
            self.id = entity_id
            self.title = title

    class FakeUser:
        def __init__(self, entity_id: int, first_name: str, username: str | None) -> None:
            self.id = entity_id
            self.first_name = first_name
            self.username = username
            self.access_hash = 500

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def iter_dialogs(self, limit: int):
            assert limit == 10
            for entity in (
                FakeChannel(101, "Alpha Channel", "alpha", 999),
                FakeChat(202, "Private Group"),
                FakeUser(303, "Alice", "alice"),
            ):
                yield SimpleNamespace(entity=entity, title=getattr(entity, "title", getattr(entity, "first_name", "")))

    tg_types = SimpleNamespace(Channel=FakeChannel, Chat=FakeChat)
    monkeypatch.setattr(
        TelegramSessionOnboardingService,
        "_load_telethon",
        staticmethod(lambda: (FakeClient, FakeStringSession, FakePasswordError, tg_types)),
    )

    rows = await TelegramSessionOnboardingService().list_dialogs(
        TelegramDialogsRequest(
            api_id=1001,
            api_hash="hash",
            session_string="session:telegram",
            limit=10,
        )
    )

    assert [row.entity_type for row in rows] == ["channel", "chat"]
    assert rows[0].settings_hint == {
        "entity_type": "channel",
        "entity_id": 101,
        "entity_access_hash": "999",
        "channel": "@alpha",
    }
    assert rows[1].settings_hint == {
        "entity_type": "chat",
        "entity_id": 202,
        "channel": "Private Group",
    }


@pytest.mark.asyncio
async def test_telegram_source_provisioning_creates_single_and_bulk_sources(async_db_session) -> None:
    async with SessionUnitOfWork(async_db_session) as uow:
        service = TelegramSourceProvisioningService(uow)

        single = await service.create_source_from_dialog(
            TelegramSourceFromDialogCreate(
                api_id=1001,
                api_hash="hash",
                session_string="session:telegram",
                dialog=TelegramDialogSelection(
                    entity_id=101,
                    entity_type="channel",
                    title="Alpha Channel",
                    username="alpha",
                    access_hash="999",
                ),
            ),
        )
        assert single.plugin_name == "telegram_user"
        assert single.display_name == "Alpha Channel"
        assert single.settings["channel"] == "@alpha"
        assert single.settings["entity_access_hash"] == "999"

        bulk = await service.bulk_subscribe(
            TelegramBulkSubscribeRequest(
                api_id=1001,
                api_hash="hash",
                session_string="session:telegram",
                dialogs=[
                    TelegramDialogSelection(
                        entity_id=101,
                        entity_type="channel",
                        title="Alpha Channel",
                        username="alpha",
                        access_hash="999",
                    ),
                    TelegramDialogSelection(
                        entity_id=202,
                        entity_type="chat",
                        title="Private Group",
                        display_name="Private Group Feed",
                    ),
                ],
            )
        )
        assert bulk.created_count == 1
        assert bulk.skipped_count == 1
        assert bulk.created[0].display_name == "Private Group Feed"
        assert bulk.results[0].status == "skipped"
        assert "already exists" in str(bulk.results[0].reason)
        assert bulk.results[1].status == "created"


def test_telegram_source_provisioning_wizard_spec() -> None:
    wizard = telegram_wizard_spec()

    assert wizard.plugin_name == "telegram_user"
    assert "channel" in wizard.supported_dialog_types
    assert wizard.steps[-1].endpoint == api_path("/news/onboarding/telegram/sources/bulk")
    assert wizard.source_payload_example["settings"]["entity_type"] == "channel"
