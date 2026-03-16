import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from src.apps.integrations.ha.application.services import HABridgeService
from src.apps.integrations.ha.bridge.runtime import HABridgeRuntime
from src.apps.integrations.ha.bridge.websocket_hub import HAWebSocketHub
from src.apps.integrations.ha.schemas import HASubscribeMessage
from src.core.bootstrap.app import create_app
from src.runtime.streams.publisher import flush_publisher, publish_event


def build_test_client(*, websocket_queue_depth: int | None = None) -> TestClient:
    app = create_app()

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    app.router.lifespan_context = _noop_lifespan
    app.state.taskiq_backfill_event = asyncio.Event()
    app.state.taskiq_worker_processes = []
    if websocket_queue_depth is not None:
        runtime = HABridgeRuntime(websocket_queue_depth=websocket_queue_depth)
        app.state.ha_bridge_runtime = runtime
        app.state.ha_bridge_service = runtime.service
    return TestClient(app)


@pytest.mark.asyncio
async def test_ha_http_endpoints_expose_protocol_surface(api_app_client, seeded_api_state) -> None:
    del seeded_api_state
    _, client = api_app_client

    health = await client.get("/ha/health")
    assert health.status_code == 200
    assert health.json()["protocol_version"] == 1
    assert health.json()["websocket_supported"] is True

    bootstrap = await client.get("/ha/bootstrap")
    assert bootstrap.status_code == 200
    bootstrap_payload = bootstrap.json()
    assert bootstrap_payload["catalog_url"] == "/api/v1/ha/catalog"
    assert bootstrap_payload["state_url"] == "/api/v1/ha/state"
    assert bootstrap_payload["capabilities"]["commands"] is True

    catalog = await client.get("/ha/catalog")
    assert catalog.status_code == 200
    catalog_payload = catalog.json()
    entity_keys = {item["entity_key"] for item in catalog_payload["entities"]}
    collection_keys = {item["collection_key"] for item in catalog_payload["collections"]}
    command_keys = {item["command_key"] for item in catalog_payload["commands"]}
    assert "system.connection" in entity_keys
    assert "portfolio.summary.open_positions" in entity_keys
    assert "settings.notifications_enabled" in entity_keys
    assert "settings.default_timeframe" in entity_keys
    assert "actions.portfolio_sync" in entity_keys
    assert "actions.market_refresh" in entity_keys
    assert collection_keys == {
        "assets.snapshot",
        "portfolio.snapshot",
        "predictions.snapshot",
        "integrations.snapshot",
    }
    assert command_keys == {
        "portfolio.sync",
        "market.refresh",
        "settings.notifications_enabled.set",
        "settings.default_timeframe.set",
    }
    assert catalog_payload["catalog_version"].startswith("sha256:")

    dashboard = await client.get("/ha/dashboard")
    assert dashboard.status_code == 200
    assert [view["view_key"] for view in dashboard.json()["views"]] == [
        "overview",
        "assets",
        "signals",
        "predictions",
        "portfolio",
        "integrations",
        "system",
    ]

    state = await client.get("/ha/state")
    assert state.status_code == 200
    state_payload = state.json()
    assert state_payload["projection_epoch"]
    assert "system.connection" in state_payload["entities"]
    assert "settings.notifications_enabled" in state_payload["entities"]
    assert "settings.default_timeframe" in state_payload["entities"]
    assert "assets.snapshot" in state_payload["collections"]


@pytest.mark.asyncio
async def test_ha_operation_endpoint_maps_core_operation_state(api_app_client, seeded_market, monkeypatch) -> None:
    del seeded_market
    _, client = api_app_client

    queued: dict[str, object] = {}

    from src.apps.market_data.tasks import run_coin_history_job

    async def fake_kiq(**kwargs) -> None:
        queued.update(kwargs)

    monkeypatch.setattr(run_coin_history_job, "kiq", fake_kiq)

    queue_response = await client.post("/coins/BTCUSD_EVT/jobs/run?mode=latest&force=false")
    assert queue_response.status_code == 202
    operation_id = queue_response.json()["operation_id"]

    operation = await client.get(f"/ha/operations/{operation_id}")
    assert operation.status_code == 200
    assert operation.json()["status"] == "queued"

    missing = await client.get("/ha/operations/missing-operation")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "operation_not_found"

    assert queued == {"symbol": "BTCUSD_EVT", "mode": "latest", "force": False, "operation_id": operation_id}


def test_ha_websocket_supports_hello_subscribe_ping_and_positive_command_ack(
    seeded_api_state,
    monkeypatch,
) -> None:
    del seeded_api_state
    queued: dict[str, object] = {}

    from src.apps.portfolio.tasks import portfolio_sync_job

    async def fake_kiq(**kwargs) -> None:
        queued.update(kwargs)

    monkeypatch.setattr(portfolio_sync_job, "kiq", fake_kiq)

    with build_test_client() as client, client.websocket_connect("/api/v1/ha/ws") as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "protocol_version": 1,
                "client": {"name": "home_assistant", "version": "0.1.0"},
            }
        )
        welcome = websocket.receive_json()
        assert welcome["type"] == "welcome"
        assert welcome["capabilities"]["collections"] is True

        websocket.send_json(
            {
                "type": "subscribe",
                "entities": ["system.connection", "portfolio.summary.open_positions"],
                "collections": ["assets.snapshot"],
                "operations": True,
            }
        )
        first = websocket.receive_json()
        second = websocket.receive_json()
        third = websocket.receive_json()
        fourth = websocket.receive_json()
        assert [item["type"] for item in (first, second, third, fourth)] == [
            "entity_state_changed",
            "entity_state_changed",
            "collection_snapshot",
            "system_health",
        ]
        assert first["sequence"] < second["sequence"] < third["sequence"] < fourth["sequence"]

        websocket.send_json({"type": "ping", "timestamp": "2026-03-15T10:00:00Z"})
        pong = websocket.receive_json()
        assert pong == {"type": "pong", "timestamp": "2026-03-15T10:00:00Z"}

        websocket.send_json(
            {
                "type": "command_execute",
                "command": "portfolio.sync",
                "payload": {},
                "request_id": "req_001",
            }
        )
        ack = websocket.receive_json()
        assert ack["type"] == "command_ack"
        assert ack["accepted"] is True
        assert isinstance(ack["operation_id"], str)

        operation_update = websocket.receive_json()
        assert operation_update["type"] == "operation_update"
        assert operation_update["operation_id"] == ack["operation_id"]
        assert operation_update["command"] == "portfolio.sync"
        assert operation_update["status"] == "queued"

    assert queued == {"operation_id": ack["operation_id"]}


def test_ha_websocket_relays_stream_events_into_live_messages(seeded_api_state) -> None:
    btc = seeded_api_state["btc"]
    signal_timestamp = seeded_api_state["signal_timestamp"]

    with build_test_client() as client, client.websocket_connect("/api/v1/ha/ws") as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "protocol_version": 1,
                "client": {"name": "home_assistant", "version": "0.1.0"},
            }
        )
        assert websocket.receive_json()["type"] == "welcome"

        websocket.send_json(
            {
                "type": "subscribe",
                "collections": ["assets.snapshot"],
            }
        )
        assert websocket.receive_json()["type"] == "collection_snapshot"
        assert websocket.receive_json()["type"] == "system_health"

        publish_event(
            "market_regime_changed",
            {
                "coin_id": int(btc.id),
                "timeframe": 15,
                "timestamp": signal_timestamp,
                "regime": "distribution",
                "confidence": 0.67,
            },
        )
        assert flush_publisher(timeout=2.0) is True

        event_message = websocket.receive_json()
        collection_message = websocket.receive_json()

        assert event_message["type"] == "event_emitted"
        assert event_message["event_type"] == "market_regime_changed"

        assert collection_message["type"] == "collection_patch"
        assert collection_message["collection_key"] == "assets.snapshot"
        assert collection_message["path"] == "BTCUSD_EVT"
        assert collection_message["value"]["market_regime"] == "distribution"
        assert collection_message["value"]["regime_confidence"] == 0.67


def test_ha_websocket_projects_pattern_state_events_into_assets_snapshot(seeded_api_state) -> None:
    btc = seeded_api_state["btc"]
    signal_timestamp = seeded_api_state["signal_timestamp"]

    with build_test_client() as client, client.websocket_connect("/api/v1/ha/ws") as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "protocol_version": 1,
                "client": {"name": "home_assistant", "version": "0.1.0"},
            }
        )
        assert websocket.receive_json()["type"] == "welcome"

        websocket.send_json(
            {
                "type": "subscribe",
                "collections": ["assets.snapshot"],
            }
        )
        assert websocket.receive_json()["type"] == "collection_snapshot"
        assert websocket.receive_json()["type"] == "system_health"

        publish_event(
            "pattern_boosted",
            {
                "coin_id": int(btc.id),
                "timeframe": 15,
                "timestamp": signal_timestamp,
                "pattern_slug": "bullish_breakout",
                "market_regime": "bull_trend",
                "confidence": 0.74,
                "factor": 1.12,
                "success_rate": 0.83,
                "total_signals": 21,
            },
        )
        assert flush_publisher(timeout=2.0) is True

        event_message = websocket.receive_json()
        collection_message = websocket.receive_json()

        assert event_message["type"] == "event_emitted"
        assert event_message["event_type"] == "pattern_boosted"
        assert collection_message["type"] == "collection_patch"
        assert collection_message["collection_key"] == "assets.snapshot"
        assert collection_message["path"] == "BTCUSD_EVT"
        assert collection_message["value"]["pattern_state"] == "boosted"
        assert collection_message["value"]["pattern_slug"] == "bullish_breakout"
        assert collection_message["value"]["pattern_factor"] == 1.12


def test_ha_websocket_supports_inline_switch_and_select_commands(seeded_api_state) -> None:
    del seeded_api_state

    with build_test_client() as client, client.websocket_connect("/api/v1/ha/ws") as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "protocol_version": 1,
                "client": {"name": "home_assistant", "version": "0.1.0"},
            }
        )
        assert websocket.receive_json()["type"] == "welcome"

        websocket.send_json(
            {
                "type": "subscribe",
                "entities": ["settings.notifications_enabled", "settings.default_timeframe", "notifications.enabled"],
                "collections": ["integrations.snapshot"],
                "operations": True,
            }
        )
        initial_types = [websocket.receive_json()["type"] for _ in range(5)]
        assert initial_types == [
            "entity_state_changed",
            "entity_state_changed",
            "entity_state_changed",
            "collection_snapshot",
            "system_health",
        ]

        websocket.send_json(
            {
                "type": "command_execute",
                "command": "settings.notifications_enabled.set",
                "payload": {"value": False},
                "request_id": "req_switch",
            }
        )
        ack = websocket.receive_json()
        switch_patch = websocket.receive_json()
        switch_entity = websocket.receive_json()
        binary_patch = websocket.receive_json()
        binary_entity = websocket.receive_json()
        collection_patch = websocket.receive_json()
        switch_operation = websocket.receive_json()

        assert ack["type"] == "command_ack"
        assert ack["accepted"] is True
        assert switch_patch["type"] == "state_patch"
        assert switch_patch["path"] == "notifications.enabled"
        assert switch_patch["value"] is False
        assert switch_entity["type"] == "entity_state_changed"
        assert switch_entity["entity_key"] == "notifications.enabled"
        assert binary_patch["type"] == "state_patch"
        assert binary_patch["path"] == "settings.notifications_enabled"
        assert binary_patch["value"] is False
        assert binary_entity["type"] == "entity_state_changed"
        assert binary_entity["entity_key"] == "settings.notifications_enabled"
        assert collection_patch["type"] == "collection_patch"
        assert collection_patch["collection_key"] == "integrations.snapshot"
        assert collection_patch["path"] == "notifications"
        assert collection_patch["value"]["enabled"] is False
        assert switch_operation["type"] == "operation_update"
        assert switch_operation["status"] == "completed"
        assert switch_operation["command"] == "settings.notifications_enabled.set"

        websocket.send_json(
            {
                "type": "command_execute",
                "command": "settings.default_timeframe.set",
                "payload": {"value": "4h"},
                "request_id": "req_select",
            }
        )
        select_ack = websocket.receive_json()
        select_patch = websocket.receive_json()
        select_entity = websocket.receive_json()
        select_operation = websocket.receive_json()

        assert select_ack["type"] == "command_ack"
        assert select_ack["accepted"] is True
        assert select_patch["type"] == "state_patch"
        assert select_patch["path"] == "settings.default_timeframe"
        assert select_patch["value"] == "4h"
        assert select_entity["type"] == "entity_state_changed"
        assert select_entity["entity_key"] == "settings.default_timeframe"
        assert select_operation["type"] == "operation_update"
        assert select_operation["status"] == "completed"
        assert select_operation["command"] == "settings.default_timeframe.set"

        state = client.get("/api/v1/ha/state")
        assert state.status_code == 200
        payload = state.json()
        assert payload["entities"]["settings.notifications_enabled"]["state"] is False
        assert payload["entities"]["notifications.enabled"]["state"] is False
        assert payload["entities"]["settings.default_timeframe"]["state"] == "4h"


@pytest.mark.asyncio
async def test_ha_websocket_hub_emits_resync_required_on_session_queue_overflow() -> None:
    service = HABridgeService()
    hub = HAWebSocketHub(service, max_queue_depth=1)
    session = await hub.register_session()
    await hub.update_subscription(
        session.session_id,
        HASubscribeMessage(type="subscribe", collections=["assets.snapshot"]),
        primed=True,
    )

    await hub.broadcast_messages(
        [
            {
                "type": "collection_patch",
                "collection_key": "assets.snapshot",
                "op": "upsert",
                "path": "BTCUSD",
                "value": {"market_regime": "bull_trend"},
            },
            {
                "type": "collection_patch",
                "collection_key": "assets.snapshot",
                "op": "upsert",
                "path": "ETHUSD",
                "value": {"market_regime": "distribution"},
            },
        ]
    )

    queued = await hub.next_message(session.session_id)
    assert queued.payload["type"] == "resync_required"
    assert queued.payload["reason"] == "queue_overflow"
    assert queued.payload["state_url"] == "/api/v1/ha/state"
    assert queued.close is True
