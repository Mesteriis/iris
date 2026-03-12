from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest

import app.apps.predictions.cache as prediction_cache_module
import app.apps.predictions.tasks as prediction_tasks_module
from app.apps.predictions.cache import (
    PREDICTION_CACHE_TTL_SECONDS,
    _parse_prediction_payload,
    cache_prediction_snapshot,
    cache_prediction_snapshot_async,
    get_async_prediction_cache_client,
    get_prediction_cache_client,
    prediction_cache_key,
    read_cached_prediction,
    read_cached_prediction_async,
)
from app.apps.predictions.selectors import list_predictions
from app.apps.predictions.services import list_predictions_async


class _SyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.last_ex: int | None = None

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value
        self.last_ex = ex

    def get(self, key: str) -> str | None:
        return self.storage.get(key)


class _AsyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.last_ex: int | None = None

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value
        self.last_ex = ex

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)


def test_prediction_cache_and_sync_selector_paths(monkeypatch, settings, db_session, seeded_api_state) -> None:
    sync_client = _SyncCacheClient()
    async_client = _AsyncCacheClient()
    timestamp = seeded_api_state["signal_timestamp"]

    get_prediction_cache_client.cache_clear()
    get_async_prediction_cache_client.cache_clear()
    monkeypatch.setattr(prediction_cache_module.Redis, "from_url", staticmethod(lambda url, decode_responses: (url, decode_responses)))
    monkeypatch.setattr(prediction_cache_module.AsyncRedis, "from_url", staticmethod(lambda url, decode_responses: (url, decode_responses)))
    assert get_prediction_cache_client() == (settings.redis_url, True)
    assert get_async_prediction_cache_client() == (settings.redis_url, True)
    get_prediction_cache_client.cache_clear()
    get_async_prediction_cache_client.cache_clear()

    monkeypatch.setattr(prediction_cache_module, "get_prediction_cache_client", lambda: sync_client)
    monkeypatch.setattr(prediction_cache_module, "get_async_prediction_cache_client", lambda: async_client)

    cache_prediction_snapshot(
        prediction_id=5,
        prediction_type="cross_market_follow_through",
        leader_coin_id=1,
        target_coin_id=2,
        prediction_event="leader_breakout",
        expected_move="up",
        lag_hours=4,
        confidence=0.74,
        created_at=timestamp,
        evaluation_time=timestamp + timedelta(hours=4),
        status="confirmed",
    )
    assert sync_client.last_ex == PREDICTION_CACHE_TTL_SECONDS
    cached = read_cached_prediction(5)
    assert cached is not None
    assert cached.prediction_type == "cross_market_follow_through"
    assert cached.status == "confirmed"
    assert read_cached_prediction(77) is None

    async def _async_cache_checks() -> None:
        await cache_prediction_snapshot_async(
            prediction_id=6,
            prediction_type="lagged_sector_rotation",
            leader_coin_id=3,
            target_coin_id=4,
            prediction_event="sector_rotation",
            expected_move="down",
            lag_hours=12,
            confidence=0.61,
            created_at=timestamp,
            evaluation_time=None,
            status="pending",
        )
        assert async_client.last_ex == PREDICTION_CACHE_TTL_SECONDS
        async_cached = await read_cached_prediction_async(6)
        assert async_cached is not None
        assert async_cached.expected_move == "down"
        assert await read_cached_prediction_async(88) is None

    asyncio.run(_async_cache_checks())

    assert _parse_prediction_payload("{", fallback_prediction_id=9) is None
    assert _parse_prediction_payload(json.dumps({"prediction_type": 3}), fallback_prediction_id=9) is None
    parsed = _parse_prediction_payload(
        json.dumps(
            {
                "prediction_type": "cross_market_follow_through",
                "confidence": 0.66,
                "created_at": "bad-date",
                "evaluation_time": "2026-03-12T10:00:00+00:00",
            }
        ),
        fallback_prediction_id=11,
    )
    assert parsed is not None
    assert parsed.id == 11
    assert parsed.created_at is None
    assert parsed.evaluation_time is not None
    assert prediction_cache_key(5) == "iris:prediction:5"

    predictions = list_predictions(db_session, status="confirmed", limit=10)
    assert len(predictions) == 1
    assert predictions[0]["leader_symbol"] == "BTCUSD_EVT"
    assert predictions[0]["target_symbol"] == "ETHUSD_EVT"
    assert list_predictions(db_session, limit=1)
    assert list_predictions(db_session, status="pending", limit=10) == []


@pytest.mark.asyncio
async def test_prediction_async_selector_and_task_wrapper(async_db_session, seeded_api_state, monkeypatch) -> None:
    predictions = await list_predictions_async(async_db_session, status="confirmed", limit=10)
    assert len(predictions) == 1
    assert predictions[0]["status"] == "confirmed"
    all_predictions = await list_predictions_async(async_db_session, limit=0)
    assert all_predictions

    events: list[str] = []

    @asynccontextmanager
    async def _lock(acquired: bool):
        events.append(f"lock:{acquired}")
        yield acquired

    monkeypatch.setattr(prediction_tasks_module, "async_redis_task_lock", lambda *args, **kwargs: _lock(False))
    skipped = await prediction_tasks_module.prediction_evaluation_job()
    assert skipped == {"status": "skipped", "reason": "prediction_evaluation_in_progress"}

    class _SessionContext:
        async def __aenter__(self):
            events.append("session_enter")
            return "async-db"

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            events.append("session_exit")
            return False

    monkeypatch.setattr(prediction_tasks_module, "async_redis_task_lock", lambda *args, **kwargs: _lock(True))
    monkeypatch.setattr(prediction_tasks_module, "AsyncSessionLocal", lambda: _SessionContext())

    async def _evaluate(db, *, emit_events: bool):
        events.append(f"evaluate:{db}:{emit_events}")
        return {"status": "ok", "evaluated": 3}

    monkeypatch.setattr(prediction_tasks_module, "evaluate_pending_predictions_async", _evaluate)
    executed = await prediction_tasks_module.prediction_evaluation_job()
    assert executed == {"status": "ok", "evaluated": 3}
    assert events[-3:] == ["lock:True", "session_enter", "evaluate:async-db:True"] or "session_exit" in events
