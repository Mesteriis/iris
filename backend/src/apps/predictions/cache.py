import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from weakref import WeakKeyDictionary

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from src.core.settings import get_settings
from src.apps.market_data.domain import ensure_utc

PREDICTION_CACHE_PREFIX = "iris:prediction"
PREDICTION_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7
_ASYNC_PREDICTION_CACHE_CLIENTS: WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncRedis] = WeakKeyDictionary()


# NOTE:
# This synchronous cache client remains intentionally for legacy sync analytics
# code running outside the main HTTP request lifecycle.
@dataclass(slots=True, frozen=True)
class PredictionCacheEntry:
    id: int
    prediction_type: str
    leader_coin_id: int
    target_coin_id: int
    prediction_event: str
    expected_move: str
    lag_hours: int
    confidence: float
    created_at: datetime | None
    evaluation_time: datetime | None
    status: str


@lru_cache(maxsize=1)
def get_prediction_cache_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_async_prediction_cache_client() -> AsyncRedis:
    settings = get_settings()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    client = _ASYNC_PREDICTION_CACHE_CLIENTS.get(loop)
    if client is None:
        client = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
        _ASYNC_PREDICTION_CACHE_CLIENTS[loop] = client
    return client


def _clear_async_prediction_cache_clients() -> None:
    _ASYNC_PREDICTION_CACHE_CLIENTS.clear()


setattr(get_async_prediction_cache_client, "cache_clear", _clear_async_prediction_cache_clients)


def prediction_cache_key(prediction_id: int) -> str:
    return f"{PREDICTION_CACHE_PREFIX}:{int(prediction_id)}"


def _serialize_prediction_payload(
    *,
    prediction_id: int,
    prediction_type: str,
    leader_coin_id: int,
    target_coin_id: int,
    prediction_event: str,
    expected_move: str,
    lag_hours: int,
    confidence: float,
    created_at: datetime | None,
    evaluation_time: datetime | None,
    status: str,
) -> str:
    return json.dumps(
        {
            "id": int(prediction_id),
            "prediction_type": prediction_type,
            "leader_coin_id": int(leader_coin_id),
            "target_coin_id": int(target_coin_id),
            "prediction_event": prediction_event,
            "expected_move": expected_move,
            "lag_hours": int(lag_hours),
            "confidence": float(confidence),
            "created_at": ensure_utc(created_at).isoformat() if created_at is not None else None,
            "evaluation_time": ensure_utc(evaluation_time).isoformat() if evaluation_time is not None else None,
            "status": status,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_prediction_payload(raw: str, *, fallback_prediction_id: int) -> PredictionCacheEntry | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None

    def _parse(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return ensure_utc(datetime.fromisoformat(value))
        except ValueError:
            return None

    prediction_type = payload.get("prediction_type")
    if not isinstance(prediction_type, str):
        return None
    return PredictionCacheEntry(
        id=int(payload.get("id", fallback_prediction_id)),
        prediction_type=prediction_type,
        leader_coin_id=int(payload.get("leader_coin_id", 0)),
        target_coin_id=int(payload.get("target_coin_id", 0)),
        prediction_event=str(payload.get("prediction_event", "")),
        expected_move=str(payload.get("expected_move", "")),
        lag_hours=int(payload.get("lag_hours", 0)),
        confidence=float(payload.get("confidence", 0.0)),
        created_at=_parse(payload.get("created_at")),
        evaluation_time=_parse(payload.get("evaluation_time")),
        status=str(payload.get("status", "pending")),
    )


def cache_prediction_snapshot(
    *,
    prediction_id: int,
    prediction_type: str,
    leader_coin_id: int,
    target_coin_id: int,
    prediction_event: str,
    expected_move: str,
    lag_hours: int,
    confidence: float,
    created_at: datetime | None,
    evaluation_time: datetime | None,
    status: str,
) -> None:
    payload = _serialize_prediction_payload(
        prediction_id=prediction_id,
        prediction_type=prediction_type,
        leader_coin_id=leader_coin_id,
        target_coin_id=target_coin_id,
        prediction_event=prediction_event,
        expected_move=expected_move,
        lag_hours=lag_hours,
        confidence=confidence,
        created_at=created_at,
        evaluation_time=evaluation_time,
        status=status,
    )
    get_prediction_cache_client().set(
        prediction_cache_key(prediction_id),
        payload,
        ex=PREDICTION_CACHE_TTL_SECONDS,
    )


async def cache_prediction_snapshot_async(
    *,
    prediction_id: int,
    prediction_type: str,
    leader_coin_id: int,
    target_coin_id: int,
    prediction_event: str,
    expected_move: str,
    lag_hours: int,
    confidence: float,
    created_at: datetime | None,
    evaluation_time: datetime | None,
    status: str,
) -> None:
    payload = _serialize_prediction_payload(
        prediction_id=prediction_id,
        prediction_type=prediction_type,
        leader_coin_id=leader_coin_id,
        target_coin_id=target_coin_id,
        prediction_event=prediction_event,
        expected_move=expected_move,
        lag_hours=lag_hours,
        confidence=confidence,
        created_at=created_at,
        evaluation_time=evaluation_time,
        status=status,
    )
    await get_async_prediction_cache_client().set(
        prediction_cache_key(prediction_id),
        payload,
        ex=PREDICTION_CACHE_TTL_SECONDS,
    )


def read_cached_prediction(prediction_id: int) -> PredictionCacheEntry | None:
    raw = get_prediction_cache_client().get(prediction_cache_key(prediction_id))
    if raw is None:
        return None
    return _parse_prediction_payload(raw, fallback_prediction_id=prediction_id)


async def read_cached_prediction_async(prediction_id: int) -> PredictionCacheEntry | None:
    raw = await get_async_prediction_cache_client().get(prediction_cache_key(prediction_id))
    if raw is None:
        return None
    return _parse_prediction_payload(raw, fallback_prediction_id=prediction_id)
