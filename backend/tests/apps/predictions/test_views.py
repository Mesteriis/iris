from __future__ import annotations

from datetime import timedelta

import pytest

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
