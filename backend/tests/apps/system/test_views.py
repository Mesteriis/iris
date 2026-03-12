from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.apps.system.views import _source_status_rows
from tests.apps.conftest import AliveProcess, SourceStatusRead


@pytest.mark.asyncio
async def test_status_and_health_endpoints(api_app_client, monkeypatch) -> None:
    app, client = api_app_client
    app.state.taskiq_worker_processes = [AliveProcess(alive=True)]

    async def fake_source_status_rows():
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

    monkeypatch.setattr("src.apps.system.views._source_status_rows", fake_source_status_rows)
    monkeypatch.setattr("src.apps.system.views.ping_database", fake_ping_database)

    status_response = await client.get("/status")
    assert status_response.status_code == 200
    assert status_response.json()["taskiq_running"] is True
    assert status_response.json()["sources"][0]["name"] == "fixture"

    health_response = await client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "healthy"}


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
        "src.apps.system.views.get_market_source_carousel",
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
        "src.apps.system.views.get_rate_limit_manager",
        lambda: SimpleNamespace(snapshot=fake_snapshot),
    )

    assert await _source_status_rows() == [
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
