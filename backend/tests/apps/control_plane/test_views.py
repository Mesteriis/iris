from __future__ import annotations

import importlib.util

import pytest
from src.apps.control_plane.api.router import build_router as build_control_plane_router
from src.apps.control_plane.contracts import build_route_key
from src.apps.control_plane.enums import EventRouteScope
from src.apps.control_plane.metrics import consumer_metric_key, route_metric_key
from src.apps.market_data.domain import utc_now
from src.core.http.launch_modes import DeploymentProfile, LaunchMode
from src.core.settings import get_settings


@pytest.mark.asyncio
async def test_control_plane_api_flow(api_app_client, isolated_control_plane_state, redis_client) -> None:
    _, client = api_app_client
    control_headers = {
        "X-IRIS-Actor": "ops",
        "X-IRIS-Access-Mode": "control",
        "X-IRIS-Reason": "integration-test",
    }

    events_response = await client.get("/control-plane/registry/events")
    assert events_response.status_code == 200
    assert any(row["event_type"] == "signal_created" for row in events_response.json())

    consumers_response = await client.get("/control-plane/registry/consumers")
    assert consumers_response.status_code == 200
    assert any(row["consumer_key"] == "hypothesis_workers" for row in consumers_response.json())

    compatibility_response = await client.get("/control-plane/registry/events/signal_created/compatible-consumers")
    assert compatibility_response.status_code == 200
    assert any(row["consumer_key"] == "hypothesis_workers" for row in compatibility_response.json())

    provider_response = await client.get("/control-plane/ai/providers")
    assert provider_response.status_code == 200
    assert isinstance(provider_response.json(), list)

    capability_response = await client.get("/control-plane/ai/capabilities")
    assert capability_response.status_code == 200
    assert any(row["capability"] == "hypothesis_generate" for row in capability_response.json())

    prompt_response = await client.get("/control-plane/ai/prompts")
    assert prompt_response.status_code == 200
    prompts = {row["name"]: row for row in prompt_response.json()}
    prompt_names = set(prompts)
    assert "notification.default" in prompt_names
    assert "brief.market" in prompt_names
    assert "explain.signal" in prompt_names
    assert prompts["notification.default"]["source"] == "db"
    assert prompts["notification.default"]["editable"] is False
    assert prompts["notification.default"]["veil_lifted"] is False

    create_payload = {
        "event_type": "signal_created",
        "consumer_key": "hypothesis_workers",
        "status": "shadow",
        "scope_type": "symbol",
        "scope_value": "BTCUSD",
        "notes": "Shadow BTC hypothesis route",
        "priority": 140,
        "shadow": {"enabled": True, "observe_only": False, "sample_rate": 1.0},
    }

    forbidden_response = await client.post("/control-plane/routes", json=create_payload)
    assert forbidden_response.status_code == 403

    incompatible_response = await client.post(
        "/control-plane/routes",
        json={**create_payload, "event_type": "news_item_normalized", "consumer_key": "decision_workers"},
        headers=control_headers,
    )
    assert incompatible_response.status_code == 400

    create_response = await client.post("/control-plane/routes", json=create_payload, headers=control_headers)
    assert create_response.status_code == 201
    created_route = create_response.json()
    original_route_key = created_route["route_key"]
    assert created_route["status"] == "shadow"
    assert created_route["scope_type"] == "symbol"

    update_payload = {
        **create_payload,
        "scope_value": "ETHUSD",
        "notes": "Updated ETH hypothesis route",
        "priority": 145,
    }
    update_response = await client.put(
        f"/control-plane/routes/{original_route_key}",
        json=update_payload,
        headers=control_headers,
    )
    assert update_response.status_code == 200
    updated_route = update_response.json()
    updated_route_key = updated_route["route_key"]
    assert updated_route_key != original_route_key
    assert updated_route["scope_value"] == "ETHUSD"

    status_response = await client.post(
        f"/control-plane/routes/{updated_route_key}/status",
        json={"status": "muted", "notes": "Muted for replay"},
        headers=control_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "muted"

    routes_response = await client.get("/control-plane/routes")
    assert routes_response.status_code == 200
    assert any(row["route_key"] == updated_route_key and row["status"] == "muted" for row in routes_response.json())

    snapshot_response = await client.get("/control-plane/topology/snapshot")
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["version_number"] == 1

    graph_response = await client.get("/control-plane/topology/graph")
    assert graph_response.status_code == 200
    graph = graph_response.json()
    assert any(edge["route_key"] == updated_route_key and edge["status"] == "muted" for edge in graph["edges"])
    assert "hypothesis_workers" in graph["compatibility"]["signal_created"]

    draft_response = await client.post(
        "/control-plane/drafts",
        json={"name": "Replay topology draft", "description": "Pause replay route", "access_mode": "control"},
        headers=control_headers,
    )
    assert draft_response.status_code == 201
    draft_id = int(draft_response.json()["id"])

    change_response = await client.post(
        f"/control-plane/drafts/{draft_id}/changes",
        json={
            "change_type": "route_status_changed",
            "target_route_key": updated_route_key,
            "payload": {"status": "paused", "notes": "Paused inside draft"},
        },
        headers=control_headers,
    )
    assert change_response.status_code == 201
    assert change_response.json()["change_type"] == "route_status_changed"

    drafts_response = await client.get("/control-plane/drafts")
    assert drafts_response.status_code == 200
    assert any(int(row["id"]) == draft_id for row in drafts_response.json())

    diff_response = await client.get(f"/control-plane/drafts/{draft_id}/diff")
    assert diff_response.status_code == 200
    assert diff_response.json()[0]["after"]["status"] == "paused"

    now = utc_now()
    redis_client.hset(
        route_metric_key(updated_route_key),
        mapping={
            "delivered_total": "3",
            "failure_total": "1",
            "shadow_total": "2",
            "last_reason": "muted",
            "last_delivered_at": now.isoformat(),
            "last_completed_at": now.isoformat(),
            "latency_total_ms": "120.0",
            "latency_count": "3",
        },
    )
    redis_client.hset(
        consumer_metric_key("hypothesis_workers"),
        mapping={
            "processed_total": "5",
            "failure_total": "1",
            "last_seen_at": now.isoformat(),
            "last_failure_at": now.isoformat(),
            "latency_total_ms": "1000.0",
            "latency_count": "5",
            "last_error": "timeout",
        },
    )

    observability_response = await client.get("/control-plane/observability")
    assert observability_response.status_code == 200
    observability = observability_response.json()
    route_metrics = {row["route_key"]: row for row in observability["routes"]}
    consumer_metrics = {row["consumer_key"]: row for row in observability["consumers"]}
    assert route_metrics[updated_route_key]["throughput"] == 3
    assert route_metrics[updated_route_key]["failure_count"] == 1
    assert route_metrics[updated_route_key]["avg_latency_ms"] == 40.0
    assert consumer_metrics["hypothesis_workers"]["processed_total"] == 5
    assert consumer_metrics["hypothesis_workers"]["avg_latency_ms"] == 200.0
    assert consumer_metrics["hypothesis_workers"]["dead"] is False
    assert observability["muted_route_count"] >= 1

    audit_response = await client.get("/control-plane/audit?limit=20")
    assert audit_response.status_code == 200
    actions = [row["action"] for row in audit_response.json()]
    assert "created" in actions
    assert "updated" in actions
    assert "status_changed" in actions


@pytest.mark.asyncio
async def test_control_plane_mutations_require_token_when_configured(
    api_app_client,
    isolated_control_plane_state,
    monkeypatch,
) -> None:
    _, client = api_app_client
    settings = get_settings()
    previous_token = settings.control_plane_token
    monkeypatch.setattr(settings, "control_plane_token", "secret-token")

    payload = {
        "event_type": "signal_created",
        "consumer_key": "hypothesis_workers",
        "status": "active",
        "scope_type": "symbol",
        "scope_value": "TOKENSEC",
    }
    headers = {"X-IRIS-Actor": "ops", "X-IRIS-Access-Mode": "control"}

    missing_token_response = await client.post("/control-plane/routes", json=payload, headers=headers)
    assert missing_token_response.status_code == 403

    allowed_response = await client.post(
        "/control-plane/routes",
        json=payload,
        headers={**headers, "X-IRIS-Control-Token": "secret-token"},
    )
    assert allowed_response.status_code == 201

    monkeypatch.setattr(settings, "control_plane_token", previous_token)


@pytest.mark.asyncio
async def test_control_plane_draft_apply_and_discard_endpoints(api_app_client, isolated_control_plane_state) -> None:
    _, client = api_app_client
    headers = {
        "X-IRIS-Actor": "ops",
        "X-IRIS-Access-Mode": "control",
        "X-IRIS-Reason": "draft-lifecycle-test",
    }

    draft_response = await client.post(
        "/control-plane/drafts",
        json={"name": "Apply lifecycle", "access_mode": "control"},
        headers=headers,
    )
    assert draft_response.status_code == 201
    apply_draft_id = int(draft_response.json()["id"])

    route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )
    change_response = await client.post(
        f"/control-plane/drafts/{apply_draft_id}/changes",
        json={
            "change_type": "route_status_changed",
            "target_route_key": route_key,
            "payload": {"status": "paused", "notes": "Paused via apply endpoint"},
        },
        headers=headers,
    )
    assert change_response.status_code == 201

    apply_response = await client.post(f"/control-plane/drafts/{apply_draft_id}/apply", headers=headers)
    assert apply_response.status_code == 200
    apply_payload = apply_response.json()
    assert apply_payload["draft"]["status"] == "applied"
    assert apply_payload["published_version_number"] == 2

    snapshot_response = await client.get("/control-plane/topology/snapshot")
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["version_number"] == 2
    applied_route = {row["route_key"]: row for row in snapshot_response.json()["routes"]}[route_key]
    assert applied_route["status"] == "paused"

    discard_response = await client.post(
        "/control-plane/drafts",
        json={"name": "Discard lifecycle", "access_mode": "control"},
        headers=headers,
    )
    assert discard_response.status_code == 201
    discard_draft_id = int(discard_response.json()["id"])

    discard_change_response = await client.post(
        f"/control-plane/drafts/{discard_draft_id}/changes",
        json={
            "change_type": "route_status_changed",
            "target_route_key": route_key,
            "payload": {"status": "muted", "notes": "Discarded change"},
        },
        headers=headers,
    )
    assert discard_change_response.status_code == 201

    discard_apply_response = await client.post(f"/control-plane/drafts/{discard_draft_id}/discard", headers=headers)
    assert discard_apply_response.status_code == 200
    assert discard_apply_response.json()["draft"]["status"] == "discarded"


@pytest.mark.asyncio
async def test_control_plane_apply_returns_concurrency_conflict_for_stale_draft(
    api_app_client,
    isolated_control_plane_state,
) -> None:
    _, client = api_app_client
    headers = {
        "X-IRIS-Actor": "ops",
        "X-IRIS-Access-Mode": "control",
        "X-IRIS-Reason": "stale-draft-test",
    }

    stale_draft_response = await client.post(
        "/control-plane/drafts",
        json={"name": "Stale draft", "access_mode": "control"},
        headers=headers,
    )
    assert stale_draft_response.status_code == 201
    stale_draft_id = int(stale_draft_response.json()["id"])

    fresh_draft_response = await client.post(
        "/control-plane/drafts",
        json={"name": "Fresh draft", "access_mode": "control"},
        headers=headers,
    )
    assert fresh_draft_response.status_code == 201
    fresh_draft_id = int(fresh_draft_response.json()["id"])

    route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )

    stale_change_response = await client.post(
        f"/control-plane/drafts/{stale_draft_id}/changes",
        json={
            "change_type": "route_status_changed",
            "target_route_key": route_key,
            "payload": {"status": "paused", "notes": "Paused by stale draft"},
        },
        headers=headers,
    )
    assert stale_change_response.status_code == 201

    fresh_change_response = await client.post(
        f"/control-plane/drafts/{fresh_draft_id}/changes",
        json={
            "change_type": "route_status_changed",
            "target_route_key": route_key,
            "payload": {"status": "muted", "notes": "Applied first to make the other draft stale"},
        },
        headers=headers,
    )
    assert fresh_change_response.status_code == 201

    fresh_apply_response = await client.post(f"/control-plane/drafts/{fresh_draft_id}/apply", headers=headers)
    assert fresh_apply_response.status_code == 200
    assert fresh_apply_response.json()["published_version_number"] == 2

    stale_apply_response = await client.post(f"/control-plane/drafts/{stale_draft_id}/apply", headers=headers)
    assert stale_apply_response.status_code == 409
    stale_payload = stale_apply_response.json()["detail"]
    assert stale_payload["code"] == "concurrency_conflict"
    assert "stale" in stale_payload["message"].lower()
    details = {item["field"]: item["value"] for item in stale_payload["details"]}
    assert details == {
        "resource_id": stale_draft_id,
        "expected_version": 1,
        "current_version": 2,
    }


def test_control_plane_api_router_is_mode_aware_and_legacy_views_removed() -> None:
    full_router = build_control_plane_router(mode=LaunchMode.FULL, profile=DeploymentProfile.PLATFORM_FULL)
    full_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in full_router.routes}
    assert any(path == "/control-plane/routes" and "POST" in methods for path, methods in full_paths)
    assert any(path == "/control-plane/ai/providers" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/control-plane/ai/prompts/{prompt_id}/activate" and "POST" in methods for path, methods in full_paths)
    assert any(path == "/control-plane/ai/prompts/{prompt_id}/lift-veil" and "POST" in methods for path, methods in full_paths)
    assert any(path == "/control-plane/ai/prompts/{prompt_id}/lower-veil" and "POST" in methods for path, methods in full_paths)

    ha_router = build_control_plane_router(mode=LaunchMode.HA_ADDON, profile=DeploymentProfile.HA_EMBEDDED)
    ha_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in ha_router.routes}
    assert not any(path == "/control-plane/routes" and "POST" in methods for path, methods in ha_paths)
    assert any(path == "/control-plane/registry/events" and "GET" in methods for path, methods in ha_paths)
    assert not any(path == "/control-plane/ai/prompts" for path, _ in ha_paths)
    assert not any(path == "/control-plane/ai/providers" for path, _ in ha_paths)
    assert not any(path == "/control-plane/ai/prompts/{prompt_id}/activate" for path, _ in ha_paths)
    assert not any(path == "/control-plane/ai/prompts/{prompt_id}/lift-veil" for path, _ in ha_paths)
    assert not any(path == "/control-plane/ai/prompts/{prompt_id}/lower-veil" for path, _ in ha_paths)

    assert importlib.util.find_spec("src.apps.control_plane.views") is None
