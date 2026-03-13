from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from src.core.http.contracts import ConsistencyClass, FreshnessClass


def analytical_metadata(
    *,
    source_updated_at: object | Iterable[object] | None,
    consistency: ConsistencyClass,
    freshness_class: FreshnessClass,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    next_generated_at = generated_at or datetime.now(timezone.utc)
    latest_source_timestamp = latest_timestamp(source_updated_at)
    return {
        "generated_at": next_generated_at,
        "consistency": consistency,
        "freshness_class": freshness_class,
        "staleness_ms": _staleness_ms(latest_source_timestamp, generated_at=next_generated_at),
    }


def latest_timestamp(values: object | Iterable[object] | None) -> datetime | None:
    if values is None:
        return None
    if isinstance(values, (str, datetime)):
        return _coerce_datetime(values)

    latest: datetime | None = None
    for value in values:
        candidate = latest_timestamp(value)
        if candidate is None:
            continue
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def _coerce_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    return None


def _staleness_ms(source_updated_at: datetime | None, *, generated_at: datetime) -> int | None:
    if source_updated_at is None:
        return None
    delta = generated_at - source_updated_at
    return max(int(delta.total_seconds() * 1000), 0)


__all__ = ["analytical_metadata", "latest_timestamp"]
