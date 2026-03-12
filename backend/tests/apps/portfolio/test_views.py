from __future__ import annotations

import pytest

from app.core.settings import get_settings


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
    assert state_response.json() == {
        "total_capital": 100000.0,
        "allocated_capital": 3200.0,
        "available_capital": 96800.0,
        "updated_at": seeded_api_state["signal_timestamp"].isoformat(),
        "open_positions": 1,
        "max_positions": get_settings().portfolio_max_positions,
    }
