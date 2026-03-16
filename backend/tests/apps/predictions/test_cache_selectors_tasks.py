import json
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
import src.apps.predictions.cache as prediction_cache_module
import src.apps.predictions.tasks as prediction_tasks_module
from src.apps.predictions.cache import (
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
from src.apps.predictions.query_services import PredictionQueryService
from src.apps.predictions.services import PredictionEvaluationBatch


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


@pytest.mark.asyncio
async def test_prediction_cache_and_query_service_paths(monkeypatch, settings, async_db_session, db_session, seeded_api_state) -> None:
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

    predictions = await PredictionQueryService(async_db_session).list_predictions(status="confirmed", limit=10)
    assert len(predictions) == 1
    assert predictions[0].leader_symbol == "BTCUSD_EVT"
    assert predictions[0].target_symbol == "ETHUSD_EVT"
    assert await PredictionQueryService(async_db_session).list_predictions(limit=1)
    assert await PredictionQueryService(async_db_session).list_predictions(status="pending", limit=10) == ()


@pytest.mark.asyncio
async def test_prediction_async_selector_and_task_wrapper(async_db_session, seeded_api_state, monkeypatch) -> None:
    predictions = await PredictionQueryService(async_db_session).list_predictions(status="confirmed", limit=10)
    assert len(predictions) == 1
    assert predictions[0].status == "confirmed"
    all_predictions = await PredictionQueryService(async_db_session).list_predictions(limit=0)
    assert all_predictions

    events: list[str] = []

    @asynccontextmanager
    async def _lock(acquired: bool):
        events.append(f"lock:{acquired}")
        yield acquired

    monkeypatch.setattr(prediction_tasks_module, "async_redis_task_lock", lambda *args, **kwargs: _lock(False))
    skipped = await prediction_tasks_module.prediction_evaluation_job()
    assert skipped == {"status": "skipped", "reason": "prediction_evaluation_in_progress"}

    class _UowContext:
        async def __aenter__(self):
            events.append("uow_enter")
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            events.append("uow_exit")
            return False

        @property
        def session(self):
            return "async-db"

        async def commit(self) -> None:
            events.append("uow_commit")

    monkeypatch.setattr(prediction_tasks_module, "async_redis_task_lock", lambda *args, **kwargs: _lock(True))
    monkeypatch.setattr(prediction_tasks_module, "AsyncUnitOfWork", lambda: _UowContext())

    class _PredictionService:
        def __init__(self, uow) -> None:
            self._uow = uow

        async def evaluate_pending_predictions(self, *, emit_events: bool, limit: int = 200):
            del limit
            events.append(f"evaluate:{self._uow.session}:{emit_events}")
            return PredictionEvaluationBatch(
                status="ok",
                evaluated=3,
                confirmed=1,
                failed=1,
                expired=1,
            )

    class _PredictionSideEffectDispatcher:
        async def apply_evaluation(self, result: PredictionEvaluationBatch) -> None:
            events.append(f"side_effects:{result.evaluated}")

    monkeypatch.setattr(prediction_tasks_module, "PredictionService", _PredictionService)
    monkeypatch.setattr(prediction_tasks_module, "PredictionSideEffectDispatcher", _PredictionSideEffectDispatcher)
    executed = await prediction_tasks_module.prediction_evaluation_job()
    assert executed == {"status": "ok", "evaluated": 3, "confirmed": 1, "failed": 1, "expired": 1}
    assert events[1:6] == [
        "lock:True",
        "uow_enter",
        "evaluate:async-db:True",
        "uow_commit",
        "uow_exit",
    ]
    assert events[-1] == "side_effects:3"
