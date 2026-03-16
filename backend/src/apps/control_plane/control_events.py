from typing import Any

from src.apps.market_data.domain import utc_now
from src.runtime.streams.publisher import publish_event

CONTROL_ROUTE_CREATED = "control.route_created"
CONTROL_ROUTE_UPDATED = "control.route_updated"
CONTROL_ROUTE_STATUS_CHANGED = "control.route_status_changed"
CONTROL_TOPOLOGY_PUBLISHED = "control.topology_published"
CONTROL_CACHE_INVALIDATED = "control.cache_invalidated"

CONTROL_EVENT_TYPES = frozenset(
    {
        CONTROL_ROUTE_CREATED,
        CONTROL_ROUTE_UPDATED,
        CONTROL_ROUTE_STATUS_CHANGED,
        CONTROL_TOPOLOGY_PUBLISHED,
        CONTROL_CACHE_INVALIDATED,
    }
)


def publish_control_event(event_type: str, payload: dict[str, Any]) -> None:
    publish_event(
        event_type,
        {
            "coin_id": int(payload.get("coin_id") or 0),
            "timeframe": int(payload.get("timeframe") or 0),
            "timestamp": payload.get("timestamp") or utc_now(),
            **payload,
        },
    )


__all__ = [
    "CONTROL_CACHE_INVALIDATED",
    "CONTROL_EVENT_TYPES",
    "CONTROL_ROUTE_CREATED",
    "CONTROL_ROUTE_STATUS_CHANGED",
    "CONTROL_ROUTE_UPDATED",
    "CONTROL_TOPOLOGY_PUBLISHED",
    "publish_control_event",
]
