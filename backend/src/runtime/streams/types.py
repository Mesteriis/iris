import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from typing import Any

from src.apps.market_data.domain import ensure_utc, utc_now
from src.core.ai import hypothesis_generation_runtime_enabled, notification_humanization_runtime_enabled
from src.core.settings import get_settings

EVENT_STREAM_NAME = get_settings().event_stream_name
INDICATOR_WORKER_GROUP = "indicator_workers"
ANALYSIS_SCHEDULER_WORKER_GROUP = "analysis_scheduler_workers"
PATTERN_WORKER_GROUP = "pattern_workers"
REGIME_WORKER_GROUP = "regime_workers"
DECISION_WORKER_GROUP = "decision_workers"
FUSION_WORKER_GROUP = "signal_fusion_workers"
PORTFOLIO_WORKER_GROUP = "portfolio_workers"
CROSS_MARKET_WORKER_GROUP = "cross_market_workers"
ANOMALY_WORKER_GROUP = "anomaly_workers"
ANOMALY_SECTOR_WORKER_GROUP = "anomaly_sector_workers"
NEWS_NORMALIZATION_WORKER_GROUP = "news_normalization_workers"
NEWS_CORRELATION_WORKER_GROUP = "news_correlation_workers"
HYPOTHESIS_WORKER_GROUP = "hypothesis_workers"
NOTIFICATION_WORKER_GROUP = "notification_workers"


def get_event_worker_groups() -> tuple[str, ...]:
    groups: list[str] = [
        INDICATOR_WORKER_GROUP,
        ANALYSIS_SCHEDULER_WORKER_GROUP,
        PATTERN_WORKER_GROUP,
        REGIME_WORKER_GROUP,
        DECISION_WORKER_GROUP,
        FUSION_WORKER_GROUP,
        PORTFOLIO_WORKER_GROUP,
        CROSS_MARKET_WORKER_GROUP,
        ANOMALY_WORKER_GROUP,
        ANOMALY_SECTOR_WORKER_GROUP,
        NEWS_NORMALIZATION_WORKER_GROUP,
        NEWS_CORRELATION_WORKER_GROUP,
    ]
    if hypothesis_generation_runtime_enabled(get_settings()):
        groups.append(HYPOTHESIS_WORKER_GROUP)
    if notification_humanization_runtime_enabled(get_settings()):
        groups.append(NOTIFICATION_WORKER_GROUP)
    return tuple(groups)


EVENT_WORKER_GROUPS = get_event_worker_groups()


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

    @property
    def event_id(self) -> str:
        return str(self.payload.get("event_id") or self.idempotency_key)

    @property
    def causation_id(self) -> str | None:
        raw = self.payload.get("causation_id")
        return str(raw) if raw is not None else None

    @property
    def correlation_id(self) -> str:
        raw = self.payload.get("correlation_id")
        if raw is not None:
            return str(raw)
        if self.causation_id is not None:
            return self.causation_id
        return self.event_id

    @property
    def parent_event_id(self) -> str | None:
        raw = self.payload.get("parent_event_id")
        return str(raw) if raw is not None else None

    @property
    def producer(self) -> str:
        raw = self.payload.get("producer")
        return str(raw) if raw is not None else "runtime.streams.publisher"

    @property
    def occurred_at(self) -> datetime:
        raw = self.payload.get("occurred_at")
        if isinstance(raw, str):
            return ensure_utc(datetime.fromisoformat(raw))
        if isinstance(raw, datetime):
            return ensure_utc(raw)
        return ensure_utc(self.timestamp)

    @property
    def symbol(self) -> str | None:
        raw = self.payload.get("symbol")
        return str(raw) if raw is not None else None

    @property
    def exchange(self) -> str | None:
        raw = self.payload.get("exchange")
        return str(raw) if raw is not None else None

    @property
    def confidence(self) -> float | None:
        raw = self.payload.get("confidence")
        return float(raw) if raw is not None else None

    @property
    def metadata(self) -> dict[str, Any]:
        raw = self.payload.get("metadata")
        return dict(raw) if isinstance(raw, dict) else {}


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
