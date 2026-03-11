from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from redis import Redis

from app.core.settings import get_settings
from app.apps.market_data.domain import ensure_utc

PREDICTION_CACHE_PREFIX = "iris:prediction"
PREDICTION_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7


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


def prediction_cache_key(prediction_id: int) -> str:
    return f"{PREDICTION_CACHE_PREFIX}:{int(prediction_id)}"


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
    payload = json.dumps(
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
    get_prediction_cache_client().set(
        prediction_cache_key(prediction_id),
        payload,
        ex=PREDICTION_CACHE_TTL_SECONDS,
    )


def read_cached_prediction(prediction_id: int) -> PredictionCacheEntry | None:
    raw = get_prediction_cache_client().get(prediction_cache_key(prediction_id))
    if raw is None:
        return None
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
        id=int(payload.get("id", prediction_id)),
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
