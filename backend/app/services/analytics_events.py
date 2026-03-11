from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.services.market_data import ensure_utc
from app.taskiq.locks import get_lock_redis

NEW_CANDLE_EVENT_HASH_KEY = "iris:analytics:new_candle_events"


@dataclass(slots=True, frozen=True)
class NewCandleEvent:
    coin_id: int
    timeframe: int
    timestamp: datetime

    @property
    def field_key(self) -> str:
        return f"{self.coin_id}:{self.timeframe}"


def _serialize_timestamp(value: datetime) -> str:
    return ensure_utc(value).isoformat()


def _parse_timestamp(value: str) -> datetime:
    return ensure_utc(datetime.fromisoformat(value))


def emit_new_candle_event(coin_id: int, timeframe: int, timestamp: datetime) -> None:
    client = get_lock_redis()
    client.eval(
        """
        local current = redis.call('HGET', KEYS[1], ARGV[1])
        if (not current) or (current < ARGV[2]) then
            redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
            return 1
        end
        return 0
        """,
        1,
        NEW_CANDLE_EVENT_HASH_KEY,
        f"{coin_id}:{timeframe}",
        _serialize_timestamp(timestamp),
    )


def list_new_candle_events() -> list[NewCandleEvent]:
    rows = get_lock_redis().hgetall(NEW_CANDLE_EVENT_HASH_KEY)
    events: list[NewCandleEvent] = []
    for field, raw_timestamp in rows.items():
        coin_id_raw, timeframe_raw = field.split(":", maxsplit=1)
        events.append(
            NewCandleEvent(
                coin_id=int(coin_id_raw),
                timeframe=int(timeframe_raw),
                timestamp=_parse_timestamp(raw_timestamp),
            )
        )
    events.sort(key=lambda item: (item.timestamp, item.coin_id, item.timeframe))
    return events


def clear_new_candle_event_if_unchanged(event: NewCandleEvent) -> bool:
    return bool(
        get_lock_redis().eval(
            """
            local current = redis.call('HGET', KEYS[1], ARGV[1])
            if current == ARGV[2] then
                redis.call('HDEL', KEYS[1], ARGV[1])
                return 1
            end
            return 0
            """,
            1,
            NEW_CANDLE_EVENT_HASH_KEY,
            event.field_key,
            _serialize_timestamp(event.timestamp),
        )
    )
