from __future__ import annotations

import importlib.util

import pytest
from src.apps.portfolio.api.router import build_router as build_portfolio_router
from src.core.http.launch_modes import DeploymentProfile, LaunchMode

from src.core.settings import get_settings


@pytest.mark.asyncio
async def test_portfolio_endpoints(api_app_client, seeded_api_state) -> None:
    _, client = api_app_client

    positions_response = await client.get("/portfolio/positions?limit=5")
    assert positions_response.status_code == 200
    positions_payload = positions_response.json()
    assert positions_payload[0]["symbol"] == "BTCUSD_EVT"
    assert positions_payload[0]["latest_decision"] == "BUY"
    assert positions_payload[0]["regime"] == "bull_trend"

    actions_response = await client.get("/portfolio/actions?limit=5")
    assert actions_response.status_code == 200
    assert actions_response.json()[0]["action"] == "OPEN_POSITION"

    state_response = await client.get("/portfolio/state")
    assert state_response.status_code == 200
    state_payload = state_response.json()
    assert state_payload["total_capital"] == 100000.0
    assert state_payload["allocated_capital"] == 3200.0
    assert state_payload["available_capital"] == 96800.0
    assert state_payload["updated_at"] == seeded_api_state["signal_timestamp"].isoformat()
    assert state_payload["open_positions"] == 1
    assert state_payload["max_positions"] == get_settings().portfolio_max_positions
    assert state_payload["consistency"] == "cached"
    assert state_payload["freshness_class"] == "near_real_time"
    assert isinstance(state_payload["generated_at"], str) and state_payload["generated_at"]
    assert isinstance(state_payload["staleness_ms"], int) and state_payload["staleness_ms"] >= 0
    assert state_response.headers["cache-control"] == "private, max-age=5, stale-while-revalidate=10"
    assert state_response.headers["etag"].startswith('W/"')
    assert "last-modified" in state_response.headers

    not_modified_response = await client.get(
        "/portfolio/state",
        headers={"If-None-Match": state_response.headers["etag"]},
    )
    assert not_modified_response.status_code == 304
    assert not_modified_response.text == ""


def test_portfolio_api_router_is_mode_agnostic_and_legacy_views_removed() -> None:
    full_router = build_portfolio_router(mode=LaunchMode.FULL, profile=DeploymentProfile.PLATFORM_FULL)
    ha_router = build_portfolio_router(mode=LaunchMode.HA_ADDON, profile=DeploymentProfile.HA_EMBEDDED)

    full_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in full_router.routes}
    ha_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in ha_router.routes}

    assert full_paths == ha_paths
    assert any(path == "/portfolio/positions" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/portfolio/actions" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/portfolio/state" and "GET" in methods for path, methods in full_paths)
    assert importlib.util.find_spec("src.apps.portfolio.views") is None
