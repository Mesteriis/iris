from datetime import datetime, timezone
import importlib.util
from types import SimpleNamespace

import pytest
from src.apps.system.api.deps import SystemStatusFacade
from src.apps.system.api.router import build_router as build_system_router
from tests.apps.conftest import AliveProcess, SourceStatusRead
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


@pytest.mark.asyncio
async def test_status_and_health_endpoints(api_app_client, monkeypatch) -> None:
    app, client = api_app_client
    app.state.taskiq_worker_processes = [AliveProcess(alive=True)]

    async def fake_source_status_rows(self):
        del self
        return [
            SourceStatusRead(
                name="fixture",
                asset_types=["crypto"],
                supported_intervals=["15m", "1h"],
                official_limit=True,
                rate_limited=False,
                cooldown_seconds=0.0,
                next_available_at=None,
                requests_per_window=120,
                window_seconds=60,
                min_interval_seconds=0.25,
                request_cost=1,
                fallback_retry_after_seconds=30,
            )
        ]

    async def fake_ping_database() -> None:
        return None

    monkeypatch.setattr("src.apps.system.api.deps.SystemStatusFacade.list_source_status_rows", fake_source_status_rows)
    monkeypatch.setattr("src.apps.system.api.deps.ping_database", fake_ping_database)

    status_response = await client.get("/status")
    assert status_response.status_code == 200
    assert status_response.json()["taskiq_running"] is True
    assert status_response.json()["sources"][0]["name"] == "fixture"

    health_response = await client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_operation_endpoints_expose_tracked_job_state(api_app_client, seeded_market, monkeypatch) -> None:
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

    status_response = await client.get(f"/operations/{operation_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["operation_id"] == operation_id
    assert status_payload["operation_type"] == "market_data.coin_history.sync"
    assert status_payload["status"] == "queued"

    result_response = await client.get(f"/operations/{operation_id}/result")
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["operation_id"] == operation_id
    assert result_payload["result"] is None

    events_response = await client.get(f"/operations/{operation_id}/events")
    assert events_response.status_code == 200
    events_payload = events_response.json()
    assert [item["event"] for item in events_payload] == ["accepted", "queued"]
    assert {item["status"] for item in events_payload} == {"accepted", "queued"}

    missing_response = await client.get("/operations/missing-operation")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"]["code"] == "resource_not_found"

    assert queued == {"symbol": "BTCUSD_EVT", "mode": "latest", "force": False, "operation_id": operation_id}


@pytest.mark.asyncio
async def test_source_status_rows_uses_carousel_and_rate_limits(monkeypatch) -> None:
    async def fake_snapshot(_name: str):
        return SimpleNamespace(
            cooldown_seconds=2.49,
            next_available_at=datetime(2026, 3, 12, 9, 30, tzinfo=timezone.utc),
            policy=SimpleNamespace(
                official_limit=True,
                requests_per_window=120,
                window_seconds=60,
                min_interval_seconds=0.25,
                request_cost=2,
                fallback_retry_after_seconds=45,
            ),
        )

    monkeypatch.setattr(
        "src.apps.system.api.deps.get_market_source_carousel",
        lambda: SimpleNamespace(
            sources={
                "fixture": SimpleNamespace(
                    asset_types={"equity", "crypto"},
                    supported_intervals={"1h", "15m"},
                )
            }
        ),
    )
    monkeypatch.setattr(
        "src.apps.system.api.deps.get_rate_limit_manager",
        lambda: SimpleNamespace(snapshot=fake_snapshot),
    )

    assert await SystemStatusFacade().list_source_status_rows() == [
        SourceStatusRead(
            name="fixture",
            asset_types=["crypto", "equity"],
            supported_intervals=["15m", "1h"],
            official_limit=True,
            rate_limited=True,
            cooldown_seconds=2.5,
            next_available_at=datetime(2026, 3, 12, 9, 30, tzinfo=timezone.utc),
            requests_per_window=120,
            window_seconds=60,
            min_interval_seconds=0.25,
            request_cost=2,
            fallback_retry_after_seconds=45,
        )
    ]


def test_system_api_router_is_mode_agnostic_and_legacy_views_removed() -> None:
    full_router = build_system_router(mode=LaunchMode.FULL, profile=DeploymentProfile.PLATFORM_FULL)
    ha_router = build_system_router(mode=LaunchMode.HA_ADDON, profile=DeploymentProfile.HA_EMBEDDED)

    full_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in full_router.routes}
    ha_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in ha_router.routes}

    assert full_paths == ha_paths
    assert any(path == "/operations/{operation_id}" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/operations/{operation_id}/events" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/system/status" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/system/health" and "GET" in methods for path, methods in full_paths)
    assert importlib.util.find_spec("src.apps.system.views") is None
