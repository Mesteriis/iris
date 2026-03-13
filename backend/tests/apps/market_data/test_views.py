from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from src.apps.market_data.views import (
    create_coin_endpoint,
    create_coin_history,
    delete_coin_endpoint,
    read_coin_history,
    run_coin_job_endpoint,
)

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
async def test_market_data_view_branches(monkeypatch) -> None:
    uow = SimpleNamespace(session=object())
    request_with_trigger = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(taskiq_backfill_event=SimpleNamespace(set=lambda: setattr(request_with_trigger.app.state, "triggered", True)))
        )
    )
    request_with_trigger.app.state.triggered = False
    payload = CoinCreateFactory.build(symbol="BTCUSD_EVT", name="Bitcoin Event Test")

    async def missing_coin(self, *_args, **_kwargs):
        return None

    async def existing_coin(self, *_args, **_kwargs):
        return SimpleNamespace(symbol="BTCUSD_EVT")

    async def created_coin(self, *_args, **_kwargs):
        return SimpleNamespace(symbol="BTCUSD_EVT")

    async def deleted(self, *_args, **_kwargs):
        return None

    async def listed_history(self, *_args, **_kwargs):
        return [{"coin_id": 1, "interval": "15m", "timestamp": "2026-03-12T00:00:00Z", "price": 1.0, "volume": None}]

    async def created_history(self, *_args, **_kwargs):
        return {"coin_id": 1, "interval": "15m", "timestamp": "2026-03-12T00:00:00Z", "price": 1.0, "volume": None}

    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", missing_coin)
    monkeypatch.setattr("src.apps.market_data.views.MarketDataService.create_coin", created_coin)
    result = await create_coin_endpoint(payload, request_with_trigger, db=uow)
    assert result.symbol == "BTCUSD_EVT"
    assert request_with_trigger.app.state.triggered is True

    request_without_trigger = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    assert (await create_coin_endpoint(payload, request_without_trigger, db=uow)).symbol == "BTCUSD_EVT"

    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", existing_coin)
    with pytest.raises(HTTPException) as conflict:
        await create_coin_endpoint(payload, request_without_trigger, db=uow)
    assert conflict.value.status_code == 409

    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", missing_coin)
    with pytest.raises(HTTPException) as delete_missing:
        await delete_coin_endpoint("BTCUSD_EVT", db=uow)
    assert delete_missing.value.status_code == 404

    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", existing_coin)
    monkeypatch.setattr("src.apps.market_data.views.MarketDataService.delete_coin", deleted)
    assert await delete_coin_endpoint("BTCUSD_EVT", db=uow) is None

    from src.apps.market_data.tasks import run_coin_history_job

    captured: dict[str, object] = {}

    async def fake_kiq(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(run_coin_history_job, "kiq", fake_kiq)
    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", missing_coin)
    with pytest.raises(HTTPException) as run_missing:
        await run_coin_job_endpoint("BTCUSD_EVT", db=uow)
    assert run_missing.value.status_code == 404

    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", existing_coin)
    queued = await run_coin_job_endpoint("BTCUSD_EVT", mode="latest", force=False, db=uow)
    assert queued["status"] == "queued"
    assert captured == {"symbol": "BTCUSD_EVT", "mode": "latest", "force": False}

    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", missing_coin)
    with pytest.raises(HTTPException) as history_missing:
        await read_coin_history("BTCUSD_EVT", db=uow)
    assert history_missing.value.status_code == 404

    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", existing_coin)
    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.list_price_history", listed_history)
    expected_history = await listed_history(None)
    assert await read_coin_history("BTCUSD_EVT", db=uow) == expected_history

    price_payload = PriceHistoryCreateFactory.build(interval="15m", price=1.0)
    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", missing_coin)
    with pytest.raises(HTTPException) as create_history_missing:
        await create_coin_history("BTCUSD_EVT", price_payload, db=uow)
    assert create_history_missing.value.status_code == 404

    async def invalid_history(self, *_args, **_kwargs):
        raise ValueError("bad history")

    monkeypatch.setattr("src.apps.market_data.views.MarketDataQueryService.get_coin_read_by_symbol", existing_coin)
    monkeypatch.setattr("src.apps.market_data.views.MarketDataService.create_price_history", invalid_history)
    with pytest.raises(HTTPException) as bad_history:
        await create_coin_history("BTCUSD_EVT", price_payload, db=uow)
    assert bad_history.value.status_code == 400

    monkeypatch.setattr("src.apps.market_data.views.MarketDataService.create_price_history", created_history)
    expected_created_history = await created_history(None)
    assert await create_coin_history("BTCUSD_EVT", price_payload, db=uow) == expected_created_history
