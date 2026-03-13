from __future__ import annotations

import importlib.util
from datetime import datetime, timezone

import pytest
from tests.apps.conftest import api_path

from src.apps.news.api.router import build_router as build_news_router
from src.apps.news.models import NewsItem, NewsSource
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


@pytest.mark.asyncio
async def test_news_endpoints(api_app_client, db_session, monkeypatch) -> None:
    _, client = api_app_client

    plugins_response = await client.get("/news/plugins")
    assert plugins_response.status_code == 200
    plugins = {row["name"]: row for row in plugins_response.json()}
    assert {"discord_bot", "telegram_user", "truth_social", "x"} <= set(plugins)
    assert plugins["truth_social"]["supported"] is False

    create_payload = {
        "plugin_name": "x",
        "display_name": "Whale Desk",
        "credentials": {"bearer_token": "x-token"},
        "settings": {"user_id": "424242"},
    }
    create_response = await client.post("/news/sources", json=create_payload)
    assert create_response.status_code == 201
    created_source = create_response.json()
    assert created_source["plugin_name"] == "x"
    assert created_source["credential_fields_present"] == ["bearer_token"]
    assert created_source["settings"] == {"user_id": "424242"}

    duplicate_response = await client.post("/news/sources", json=create_payload)
    assert duplicate_response.status_code == 400
    assert "already exists" in duplicate_response.json()["detail"]["message"]

    unsupported_response = await client.post(
        "/news/sources",
        json={
            "plugin_name": "truth_social",
            "display_name": "Trump Feed",
            "credentials": {},
            "settings": {},
        },
    )
    assert unsupported_response.status_code == 400
    assert "developer API" in unsupported_response.json()["detail"]["message"]

    sources_response = await client.get("/news/sources")
    assert sources_response.status_code == 200
    assert [row["display_name"] for row in sources_response.json()] == ["Whale Desk"]

    source_id = int(created_source["id"])
    patch_response = await client.patch(
        f"/news/sources/{source_id}",
        json={
            "display_name": "Whale Desk Prime",
            "enabled": False,
            "settings": {"max_results": 20},
            "credentials": {"access_token": "user-token"},
            "reset_cursor": True,
            "clear_error": True,
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["display_name"] == "Whale Desk Prime"
    assert patch_response.json()["enabled"] is False
    assert patch_response.json()["status"] == "disabled"
    assert patch_response.json()["settings"] == {"user_id": "424242", "max_results": 20}

    db_session.add(
        NewsItem(
            source_id=source_id,
            plugin_name="x",
            external_id="tweet-1",
            published_at=datetime(2026, 3, 12, 12, 30, tzinfo=timezone.utc),
            author_handle="macrodesk",
            channel_name="Whale Desk Prime",
            title=None,
            content_text="Watching $BTC and $ETH flows",
            url="https://x.com/i/web/status/1",
            symbol_hints=["BTC", "ETH"],
            payload_json={"kind": "tweet"},
        )
    )
    db_session.commit()

    items_response = await client.get(f"/news/items?source_id={source_id}&limit=10")
    assert items_response.status_code == 200
    items = items_response.json()
    assert len(items) == 1
    assert items[0]["external_id"] == "tweet-1"
    assert items[0]["symbol_hints"] == ["BTC", "ETH"]
    assert items[0]["normalization_status"] == "pending"
    assert items[0]["links"] == []

    queued: dict[str, object] = {}

    from src.apps.news.tasks import poll_news_source_job

    async def fake_kiq(**kwargs):
        queued.update(kwargs)

    monkeypatch.setattr(poll_news_source_job, "kiq", fake_kiq)

    queued_response = await client.post(f"/news/sources/{source_id}/jobs/run?limit=25")
    assert queued_response.status_code == 202
    assert queued_response.json() == {
        "status": "queued",
        "source_id": source_id,
        "limit": 25,
    }
    assert queued == {"source_id": source_id, "limit": 25}

    missing_response = await client.post("/news/sources/999999/jobs/run")
    assert missing_response.status_code == 404

    assert (await client.patch("/news/sources/999999", json={"enabled": True})).status_code == 404
    assert (await client.delete(f"/news/sources/{source_id}")).status_code == 204
    assert (await client.delete(f"/news/sources/{source_id}")).status_code == 404


@pytest.mark.asyncio
async def test_news_list_endpoint_handles_empty_state(api_app_client) -> None:
    _, client = api_app_client

    response = await client.get("/news/items")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_telegram_onboarding_endpoints(api_app_client, monkeypatch) -> None:
    _, client = api_app_client

    async def fake_request(self, payload):
        del self
        return {
            "status": "code_sent",
            "phone_number": payload.phone_number,
            "phone_code_hash": "hash-telegram",
        }

    async def fake_confirm(self, payload):
        del self
        return {
            "status": "authorized",
            "session_string": "session-telegram",
            "user_id": 17,
            "username": "iris_user",
            "display_name": "Iris User",
        }

    async def fake_dialogs(self, payload):
        del self
        return [
            {
                "entity_id": 101,
                "entity_type": "channel",
                "title": "Alpha Channel",
                "username": "alpha",
                "access_hash": "999",
                "selectable": True,
                "settings_hint": {
                    "entity_type": "channel",
                    "entity_id": 101,
                    "entity_access_hash": "999",
                    "channel": "@alpha",
                },
            }
        ]

    monkeypatch.setattr("src.apps.news.api.deps.TelegramSessionOnboardingService.request_code", fake_request)
    monkeypatch.setattr("src.apps.news.api.deps.TelegramSessionOnboardingService.confirm_code", fake_confirm)
    monkeypatch.setattr("src.apps.news.api.deps.TelegramSessionOnboardingService.list_dialogs", fake_dialogs)

    request_response = await client.post(
        "/news/onboarding/telegram/session/request",
        json={"api_id": 1001, "api_hash": "hash", "phone_number": "+10000000000"},
    )
    assert request_response.status_code == 200
    assert request_response.json() == {
        "status": "code_sent",
        "phone_number": "+10000000000",
        "phone_code_hash": "hash-telegram",
    }

    confirm_response = await client.post(
        "/news/onboarding/telegram/session/confirm",
        json={
            "api_id": 1001,
            "api_hash": "hash",
            "phone_number": "+10000000000",
            "phone_code_hash": "hash-telegram",
            "code": "12345",
        },
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "authorized"
    assert confirm_response.json()["session_string"] == "session-telegram"

    dialogs_response = await client.post(
        "/news/onboarding/telegram/dialogs",
        json={
            "api_id": 1001,
            "api_hash": "hash",
            "session_string": "session-telegram",
            "limit": 50,
        },
    )
    assert dialogs_response.status_code == 200
    assert dialogs_response.json()[0]["entity_type"] == "channel"
    assert dialogs_response.json()[0]["settings_hint"]["entity_access_hash"] == "999"


@pytest.mark.asyncio
async def test_telegram_source_provisioning_endpoints(api_app_client) -> None:
    _, client = api_app_client

    wizard_response = await client.get("/news/onboarding/telegram/wizard")
    assert wizard_response.status_code == 200
    wizard_payload = wizard_response.json()
    assert wizard_payload["plugin_name"] == "telegram_user"
    assert wizard_payload["steps"][-1]["endpoint"] == api_path("/news/onboarding/telegram/sources/bulk")

    single_response = await client.post(
        "/news/onboarding/telegram/sources",
        json={
            "api_id": 1001,
            "api_hash": "hash",
            "session_string": "session:telegram",
            "dialog": {
                "entity_id": 101,
                "entity_type": "channel",
                "title": "Alpha Channel",
                "username": "alpha",
                "access_hash": "999",
            },
        },
    )
    assert single_response.status_code == 201
    assert single_response.json()["plugin_name"] == "telegram_user"
    assert single_response.json()["settings"]["channel"] == "@alpha"

    bulk_response = await client.post(
        "/news/onboarding/telegram/sources/bulk",
        json={
            "api_id": 1001,
            "api_hash": "hash",
            "session_string": "session:telegram",
            "dialogs": [
                {
                    "entity_id": 101,
                    "entity_type": "channel",
                    "title": "Alpha Channel",
                    "username": "alpha",
                    "access_hash": "999",
                },
                {
                    "entity_id": 202,
                    "entity_type": "chat",
                    "title": "Private Group",
                    "display_name": "Private Group Feed",
                },
            ],
        },
    )
    assert bulk_response.status_code == 201
    payload = bulk_response.json()
    assert payload["created_count"] == 1
    assert payload["skipped_count"] == 1
    assert payload["created"][0]["display_name"] == "Private Group Feed"
    assert payload["results"][0]["status"] == "skipped"
    assert payload["results"][1]["status"] == "created"


def test_news_api_router_is_mode_aware_and_legacy_views_removed() -> None:
    full_router = build_news_router(mode=LaunchMode.FULL, profile=DeploymentProfile.PLATFORM_FULL)
    full_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in full_router.routes}
    assert any(path == "/news/sources" and "POST" in methods for path, methods in full_paths)
    assert any(path == "/news/onboarding/telegram/wizard" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/news/sources/{source_id}/jobs/run" and "POST" in methods for path, methods in full_paths)

    ha_router = build_news_router(mode=LaunchMode.HA_ADDON, profile=DeploymentProfile.HA_EMBEDDED)
    ha_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in ha_router.routes}
    assert not any(path == "/news/sources" and "POST" in methods for path, methods in ha_paths)
    assert not any(path == "/news/onboarding/telegram/wizard" and "GET" in methods for path, methods in ha_paths)
    assert not any(path == "/news/sources/{source_id}/jobs/run" and "POST" in methods for path, methods in ha_paths)
    assert any(path == "/news/plugins" and "GET" in methods for path, methods in ha_paths)
    assert any(path == "/news/items" and "GET" in methods for path, methods in ha_paths)

    assert importlib.util.find_spec("src.apps.news.views") is None
