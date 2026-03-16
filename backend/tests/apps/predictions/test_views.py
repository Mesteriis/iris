import importlib.util
from datetime import timedelta

import pytest
from src.apps.predictions.api.router import build_router as build_predictions_router
from src.core.http.launch_modes import DeploymentProfile, LaunchMode

from tests.factories.base import json_utc


@pytest.mark.asyncio
async def test_prediction_endpoints(api_app_client, seeded_api_state) -> None:
    _, client = api_app_client

    predictions_response = await client.get("/predictions?status=confirmed&limit=5")
    assert predictions_response.status_code == 200
    assert predictions_response.json() == [
        {
            "id": predictions_response.json()[0]["id"],
            "prediction_type": "cross_market_follow_through",
            "leader_coin_id": seeded_api_state["btc"].id,
            "leader_symbol": "BTCUSD_EVT",
            "target_coin_id": seeded_api_state["eth"].id,
            "target_symbol": "ETHUSD_EVT",
            "prediction_event": "leader_breakout",
            "expected_move": "up",
            "lag_hours": 4,
            "confidence": 0.74,
            "created_at": json_utc(seeded_api_state["signal_timestamp"]),
            "evaluation_time": json_utc(seeded_api_state["signal_timestamp"] + timedelta(hours=4)),
            "status": "confirmed",
            "actual_move": 0.046,
            "success": True,
            "profit": 0.046,
            "evaluated_at": json_utc(seeded_api_state["signal_timestamp"] + timedelta(hours=4)),
        }
    ]


def test_predictions_api_router_is_mode_agnostic_and_legacy_views_removed() -> None:
    full_router = build_predictions_router(mode=LaunchMode.FULL, profile=DeploymentProfile.PLATFORM_FULL)
    ha_router = build_predictions_router(mode=LaunchMode.HA_ADDON, profile=DeploymentProfile.HA_EMBEDDED)

    full_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in full_router.routes}
    ha_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in ha_router.routes}

    assert full_paths == ha_paths
    assert any(path == "/predictions" and "GET" in methods for path, methods in full_paths)
    assert importlib.util.find_spec("src.apps.predictions.views") is None
