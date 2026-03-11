from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from typing import Any

from app.core.config import get_settings
from app.services.market_data import ensure_utc, utc_now

EVENT_STREAM_NAME = get_settings().event_stream_name
INDICATOR_WORKER_GROUP = "indicator_workers"
PATTERN_WORKER_GROUP = "pattern_workers"
REGIME_WORKER_GROUP = "regime_workers"
DECISION_WORKER_GROUP = "decision_workers"
EVENT_WORKER_GROUPS = (
    INDICATOR_WORKER_GROUP,
    PATTERN_WORKER_GROUP,
    REGIME_WORKER_GROUP,
    DECISION_WORKER_GROUP,
)


@dataclass(frozen=True, slots=True)
class IrisEvent:
    stream_id: str
    event_type: str
    coin_id: int
    timeframe: int
    timestamp: datetime
    payload: dict[str, Any]

    @property
    def idempotency_key(self) -> str:
        payload_hash = sha1(
            json.dumps(self.payload, ensure_ascii=True, sort_keys=True).encode("ascii", errors="ignore")
        ).hexdigest()
        return f"{self.event_type}:{self.coin_id}:{self.timeframe}:{ensure_utc(self.timestamp).isoformat()}:{payload_hash}"


def serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def deserialize_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def build_event_fields(event_type: str, payload: dict[str, Any]) -> dict[str, str]:
    event_payload = dict(payload)
    coin_id = int(event_payload.pop("coin_id"))
    timeframe = int(event_payload.pop("timeframe"))
    timestamp_raw = event_payload.pop("timestamp")
    timestamp = (
        ensure_utc(datetime.fromisoformat(timestamp_raw))
        if isinstance(timestamp_raw, str)
        else ensure_utc(timestamp_raw)
    )
    return {
        "event_type": str(event_type),
        "coin_id": str(coin_id),
        "timeframe": str(timeframe),
        "timestamp": timestamp.isoformat(),
        "created_at": utc_now().isoformat(),
        "payload": serialize_payload(event_payload),
    }


def parse_stream_message(stream_id: str, fields: dict[str, str]) -> IrisEvent:
    return IrisEvent(
        stream_id=stream_id,
        event_type=str(fields["event_type"]),
        coin_id=int(fields["coin_id"]),
        timeframe=int(fields["timeframe"]),
        timestamp=ensure_utc(datetime.fromisoformat(fields["timestamp"])),
        payload=deserialize_payload(fields.get("payload")),
    )
