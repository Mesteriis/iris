from __future__ import annotations

from datetime import timedelta
import importlib.util
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from src.apps.market_data.api.command_endpoints import (
    create_coin_endpoint,
    create_coin_history,
    delete_coin_endpoint,
)
from src.apps.market_data.api.deps import MarketDataBackfillTrigger
from src.apps.market_data.api.job_endpoints import run_coin_job_endpoint
from src.apps.market_data.api.read_endpoints import read_coin_history
from src.apps.market_data.api.router import build_router as build_market_data_router
from src.core.http.launch_modes import DeploymentProfile, LaunchMode

from tests.factories.market_data import CoinCreateFactory, PriceHistoryCreateFactory


@pytest.mark.asyncio
async def test_market_data_endpoints(api_app_client, seeded_market, monkeypatch) -> None:
    app, client = api_app_client
    queued: dict[str, object] = {}

    from src.apps.market_data.tasks import run_coin_history_job

    async def fake_kiq(**kwargs):
        queued.update(kwargs)

    monkeypatch.setattr(run_coin_history_job, "kiq", fake_kiq)

    initial = await client.get("/coins")
    assert initial.status_code == 200
    assert {"BTCUSD_EVT", "ETHUSD_EVT", "SOLUSD_EVT"} <= {row["symbol"] for row in initial.json()}

    coin_payload = CoinCreateFactory.build(
        symbol="ADAUSD_EVT",
        name="Cardano Event Test",
        theme="layer1",
        sector="smart_contract",
        sort_order=5,
        candles=[{"interval": "15m", "retention_bars": 300}],
    )
    create_response = await client.post("/coins", json=coin_payload.model_dump(mode="json"))
    assert create_response.status_code == 201
    assert create_response.json()["symbol"] == "ADAUSD_EVT"
    assert app.state.taskiq_backfill_event.is_set()

    delattr(app.state, "taskiq_backfill_event")
    second_payload = CoinCreateFactory.build(symbol="XRPUSD_EVT", name="Ripple Event Test", theme="payments")
    create_without_trigger_response = await client.post("/coins", json=second_payload.model_dump(mode="json"))
    assert create_without_trigger_response.status_code == 201

    duplicate_response = await client.post("/coins", json=coin_payload.model_dump(mode="json"))
    assert duplicate_response.status_code == 409

    history_response = await client.get("/coins/BTCUSD_EVT/history")
    assert history_response.status_code == 200
    latest_timestamp = seeded_market["BTCUSD_EVT"]["latest_timestamp"]
    assert latest_timestamp is not None

    history_payload = PriceHistoryCreateFactory.build(
        interval="15m",
        timestamp=latest_timestamp + timedelta(minutes=15),
        price=123456.0,
        volume=987.0,
    )
    create_history_response = await client.post("/coins/BTCUSD_EVT/history", json=history_payload.model_dump(mode="json"))
    assert create_history_response.status_code == 201
    assert create_history_response.json()["price"] == 123456.0

    invalid_payload = PriceHistoryCreateFactory.build(
        interval="1h",
        timestamp=latest_timestamp + timedelta(hours=1),
        price=123456.0,
    )
    invalid_history_response = await client.post("/coins/BTCUSD_EVT/history", json=invalid_payload.model_dump(mode="json"))
    assert invalid_history_response.status_code == 400

    missing_history_payload = PriceHistoryCreateFactory.build(
        interval="15m",
        timestamp=latest_timestamp + timedelta(minutes=30),
        price=42.0,
    )
    missing_create_history_response = await client.post(
        "/coins/MISSING_EVT/history",
        json=missing_history_payload.model_dump(mode="json"),
    )
    assert missing_create_history_response.status_code == 404

    queued_response = await client.post("/coins/BTCUSD_EVT/jobs/run?mode=latest&force=false")
    assert queued_response.status_code == 202
    assert queued == {"symbol": "BTCUSD_EVT", "mode": "latest", "force": False}

    assert (await client.post("/coins/MISSING_EVT/jobs/run")).status_code == 404
    assert (await client.get("/coins/MISSING_EVT/history")).status_code == 404

    assert (await client.delete("/coins/ADAUSD_EVT")).status_code == 204
    assert (await client.delete("/coins/ADAUSD_EVT")).status_code == 404


@pytest.mark.asyncio
async def test_market_data_view_branches() -> None:
    class TrackingUow:
        def __init__(self) -> None:
            self._actions = []

        def add_after_commit_action(self, action) -> None:
            self._actions.append(action)

        async def commit(self) -> None:
            actions = list(self._actions)
            self._actions.clear()
            for action in actions:
                result = action()
                if hasattr(result, "__await__"):
                    await result

    trigger_state = SimpleNamespace(triggered=False)
    trigger = MarketDataBackfillTrigger(
        event=SimpleNamespace(set=lambda: setattr(trigger_state, "triggered", True))
    )
    uow = TrackingUow()
    payload = CoinCreateFactory.build(symbol="BTCUSD_EVT", name="Bitcoin Event Test")

    async def missing_coin(*_args, **_kwargs):
        return None

    async def existing_coin(*_args, **_kwargs):
        return SimpleNamespace(symbol="BTCUSD_EVT")

    async def created_coin(*_args, **_kwargs):
        return {
            "id": 1,
            "symbol": "BTCUSD_EVT",
            "name": "Bitcoin Event Test",
            "asset_type": "crypto",
            "theme": "core",
            "sector": "store_of_value",
            "source": "default",
            "enabled": True,
            "sort_order": 0,
            "auto_watch_enabled": False,
            "auto_watch_source": None,
            "created_at": "2026-03-12T00:00:00Z",
            "history_backfill_completed_at": None,
            "last_history_sync_at": None,
            "next_history_sync_at": None,
            "last_history_sync_error": None,
            "candles": [{"interval": "15m", "retention_bars": 20160}],
        }

    async def deleted(*_args, **_kwargs):
        return True

    async def missing_delete(*_args, **_kwargs):
        return False

    async def listed_history(*_args, **_kwargs):
        return [{"coin_id": 1, "interval": "15m", "timestamp": "2026-03-12T00:00:00Z", "price": 1.0, "volume": None}]

    async def created_history(*_args, **_kwargs):
        return {"coin_id": 1, "interval": "15m", "timestamp": "2026-03-12T00:00:00Z", "price": 1.0, "volume": None}

    commands = SimpleNamespace(
        service=SimpleNamespace(
            create_coin=created_coin,
            delete_coin=deleted,
            create_price_history=created_history,
        ),
        uow=uow,
        backfill_trigger=trigger,
    )
    query_service = SimpleNamespace(get_coin_read_by_symbol=missing_coin, list_price_history=listed_history)
    dispatcher_calls: dict[str, object] = {}

    async def fake_dispatch_coin_history(**kwargs):
        dispatcher_calls.update(kwargs)

    dispatcher = SimpleNamespace(dispatch_coin_history=fake_dispatch_coin_history)

    result = await create_coin_endpoint(payload, commands=commands, query_service=query_service)
    assert result.symbol == "BTCUSD_EVT"
    assert trigger_state.triggered is True

    trigger_state.triggered = False
    commands_without_trigger = SimpleNamespace(
        service=commands.service,
        uow=TrackingUow(),
        backfill_trigger=MarketDataBackfillTrigger(event=None),
    )
    assert (await create_coin_endpoint(payload, commands=commands_without_trigger, query_service=query_service)).symbol == "BTCUSD_EVT"
    assert trigger_state.triggered is False

    query_service.get_coin_read_by_symbol = existing_coin
    with pytest.raises(HTTPException) as conflict:
        await create_coin_endpoint(payload, commands=commands_without_trigger, query_service=query_service)
    assert conflict.value.status_code == 409

    query_service.get_coin_read_by_symbol = missing_coin
    commands.service.delete_coin = missing_delete
    with pytest.raises(HTTPException) as delete_missing:
        await delete_coin_endpoint("BTCUSD_EVT", commands=commands)
    assert delete_missing.value.status_code == 404

    commands.service.delete_coin = deleted
    assert await delete_coin_endpoint("BTCUSD_EVT", commands=commands) is None

    query_service.get_coin_read_by_symbol = missing_coin
    with pytest.raises(HTTPException) as run_missing:
        await run_coin_job_endpoint("BTCUSD_EVT", dispatcher=dispatcher, query_service=query_service)
    assert run_missing.value.status_code == 404

    query_service.get_coin_read_by_symbol = existing_coin
    queued = await run_coin_job_endpoint(
        "BTCUSD_EVT",
        mode="latest",
        force=False,
        dispatcher=dispatcher,
        query_service=query_service,
    )
    assert queued.status == "queued"
    assert dispatcher_calls == {"symbol": "BTCUSD_EVT", "mode": "latest", "force": False}

    query_service.get_coin_read_by_symbol = missing_coin
    with pytest.raises(HTTPException) as history_missing:
        await read_coin_history("BTCUSD_EVT", service=query_service)
    assert history_missing.value.status_code == 404

    query_service.get_coin_read_by_symbol = existing_coin
    query_service.list_price_history = listed_history
    history = await read_coin_history("BTCUSD_EVT", service=query_service)
    assert len(history) == 1
    assert history[0].price == 1.0

    price_payload = PriceHistoryCreateFactory.build(interval="15m", price=1.0)
    query_service.get_coin_read_by_symbol = missing_coin
    with pytest.raises(HTTPException) as create_history_missing:
        await create_coin_history("BTCUSD_EVT", price_payload, commands=commands, query_service=query_service)
    assert create_history_missing.value.status_code == 404

    async def invalid_history(*_args, **_kwargs):
        raise ValueError("bad history")

    query_service.get_coin_read_by_symbol = existing_coin
    commands.service.create_price_history = invalid_history
    with pytest.raises(HTTPException) as bad_history:
        await create_coin_history("BTCUSD_EVT", price_payload, commands=commands, query_service=query_service)
    assert bad_history.value.status_code == 400

    commands.service.create_price_history = created_history
    created = await create_coin_history("BTCUSD_EVT", price_payload, commands=commands, query_service=query_service)
    assert created.price == 1.0


def test_market_data_api_router_is_mode_agnostic_and_legacy_views_removed() -> None:
    full_router = build_market_data_router(mode=LaunchMode.FULL, profile=DeploymentProfile.PLATFORM_FULL)
    ha_router = build_market_data_router(mode=LaunchMode.HA_ADDON, profile=DeploymentProfile.HA_EMBEDDED)

    full_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in full_router.routes}
    ha_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in ha_router.routes}

    assert full_paths == ha_paths
    assert any(path == "/coins" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/coins/{symbol}/jobs/run" and "POST" in methods for path, methods in full_paths)
    assert any(path == "/coins/{symbol}/history" and "POST" in methods for path, methods in full_paths)
    assert importlib.util.find_spec("src.apps.market_data.views") is None
