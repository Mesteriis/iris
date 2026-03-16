from datetime import timedelta
from typing import Any

from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_structure.constants import (
    DEFAULT_MARKET_STRUCTURE_FAILURE_BACKOFF_BASE_SECONDS,
    DEFAULT_MARKET_STRUCTURE_FAILURE_BACKOFF_MAX_SECONDS,
    DEFAULT_MARKET_STRUCTURE_QUARANTINE_AFTER_FAILURES,
    MARKET_STRUCTURE_ALERT_KIND_ERROR,
    MARKET_STRUCTURE_ALERT_KIND_QUARANTINED,
    MARKET_STRUCTURE_ALERT_KIND_STALE,
    MARKET_STRUCTURE_HEALTH_STATUS_DISABLED,
    MARKET_STRUCTURE_HEALTH_STATUS_ERROR,
    MARKET_STRUCTURE_HEALTH_STATUS_HEALTHY,
    MARKET_STRUCTURE_HEALTH_STATUS_IDLE,
    MARKET_STRUCTURE_HEALTH_STATUS_QUARANTINED,
    MARKET_STRUCTURE_HEALTH_STATUS_STALE,
    MARKET_STRUCTURE_MANUAL_INGEST_MODE_WEBHOOK,
    MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
    MARKET_STRUCTURE_SOURCE_STATUS_ACTIVE,
    MARKET_STRUCTURE_SOURCE_STATUS_DISABLED,
    MARKET_STRUCTURE_SOURCE_STATUS_ERROR,
    MARKET_STRUCTURE_SOURCE_STATUS_QUARANTINED,
)
from src.apps.market_structure.contracts import MarketStructureSourceHealthRead
from src.apps.market_structure.plugins import get_market_structure_plugin
from src.core.settings import get_settings


def merge_market_structure_mapping(base: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if patch is None:
        return merged
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def market_structure_source_status(source) -> str:
    if source.quarantined_at is not None:
        return MARKET_STRUCTURE_SOURCE_STATUS_QUARANTINED
    if not source.enabled:
        return MARKET_STRUCTURE_SOURCE_STATUS_DISABLED
    if source.last_error:
        return MARKET_STRUCTURE_SOURCE_STATUS_ERROR
    return MARKET_STRUCTURE_SOURCE_STATUS_ACTIVE


def market_structure_credential_fields_present(credentials: dict[str, Any]) -> list[str]:
    return sorted(key for key, value in credentials.items() if value not in (None, "", [], {}, ()))


def isoformat_or_none(value) -> str | None:
    return ensure_utc(value).isoformat() if value is not None else None


def market_structure_is_quarantined(source) -> bool:
    return source.quarantined_at is not None


def market_structure_backoff_until(source):
    return ensure_utc(source.backoff_until) if source.backoff_until is not None else None


def market_structure_backoff_active(source, *, now) -> bool:
    backoff_until = market_structure_backoff_until(source)
    return backoff_until is not None and backoff_until > ensure_utc(now)


def market_structure_backoff_seconds_for_failure_count(consecutive_failures: int) -> int:
    settings = get_settings()
    base_seconds = max(
        int(getattr(settings, "taskiq_market_structure_failure_backoff_base_seconds", 0))
        or DEFAULT_MARKET_STRUCTURE_FAILURE_BACKOFF_BASE_SECONDS,
        0,
    )
    max_seconds = max(
        int(getattr(settings, "taskiq_market_structure_failure_backoff_max_seconds", 0))
        or DEFAULT_MARKET_STRUCTURE_FAILURE_BACKOFF_MAX_SECONDS,
        base_seconds,
    )
    if consecutive_failures <= 0 or base_seconds <= 0:
        return 0
    return min(base_seconds * (2 ** max(consecutive_failures - 1, 0)), max_seconds)


def market_structure_quarantine_after_failures() -> int:
    settings = get_settings()
    return max(
        int(getattr(settings, "taskiq_market_structure_quarantine_after_failures", 0))
        or DEFAULT_MARKET_STRUCTURE_QUARANTINE_AFTER_FAILURES,
        0,
    )


def market_structure_source_provider(source) -> str:
    settings = dict(source.settings_json or {})
    return str(settings.get("provider") or settings.get("venue") or MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH).strip().lower()


def market_structure_source_ingest_mode(source) -> str:
    settings = dict(source.settings_json or {})
    explicit = str(settings.get("ingest_mode") or "").strip().lower()
    if explicit:
        return explicit
    plugin_cls = get_market_structure_plugin(source.plugin_name)
    if plugin_cls is not None and plugin_cls.descriptor.supports_polling:
        return "polling"
    return "manual"


def market_structure_stale_after_seconds(source) -> int | None:
    settings = get_settings()
    timeframe_minutes = max(int((source.settings_json or {}).get("timeframe") or 15), 1)
    timeframe_seconds = timeframe_minutes * 60
    ingest_mode = market_structure_source_ingest_mode(source)
    if ingest_mode == MARKET_STRUCTURE_MANUAL_INGEST_MODE_WEBHOOK:
        return max(timeframe_seconds * 6, 1800)
    plugin_cls = get_market_structure_plugin(source.plugin_name)
    if plugin_cls is not None and plugin_cls.descriptor.supports_polling:
        return max(int(settings.taskiq_market_structure_snapshot_poll_interval_seconds) * 3, timeframe_seconds * 3)
    return max(timeframe_seconds * 12, 3600)


def build_market_structure_source_health(source, *, now=None) -> MarketStructureSourceHealthRead:
    current_time = ensure_utc(now or utc_now())
    last_activity_at = source.last_polled_at
    last_success_at = source.last_success_at
    last_snapshot_at = source.last_snapshot_at
    stale_after_seconds = market_structure_stale_after_seconds(source)
    ingest_mode = market_structure_source_ingest_mode(source)
    backoff_until = market_structure_backoff_until(source)
    backoff_active = market_structure_backoff_active(source, now=current_time)
    consecutive_failures = int(source.consecutive_failures or 0)
    quarantined = market_structure_is_quarantined(source)
    if quarantined:
        status = MARKET_STRUCTURE_HEALTH_STATUS_QUARANTINED
        severity = "critical"
        stale = False
        message = str(source.quarantine_reason or "Source was quarantined after repeated polling failures.")
    elif not source.enabled:
        status = MARKET_STRUCTURE_HEALTH_STATUS_DISABLED
        severity = "info"
        stale = False
        message = "Source is disabled."
    elif source.last_error:
        status = MARKET_STRUCTURE_HEALTH_STATUS_ERROR
        severity = "error"
        stale = False
        if backoff_active and backoff_until is not None:
            retry_in_seconds = max(int((backoff_until - current_time).total_seconds()), 0)
            message = f"{source.last_error}. Retry scheduled in {retry_in_seconds}s."
        else:
            message = str(source.last_error)
    else:
        reference_candidates = [value for value in (last_snapshot_at, last_success_at) if value is not None]
        reference_time = max((ensure_utc(value) for value in reference_candidates), default=None)
        if reference_time is None:
            status = MARKET_STRUCTURE_HEALTH_STATUS_IDLE
            severity = "info"
            stale = False
            message = "Waiting for first successful snapshot."
        else:
            age_seconds = max(int((current_time - ensure_utc(reference_time)).total_seconds()), 0)
            if stale_after_seconds is not None and age_seconds > stale_after_seconds:
                status = MARKET_STRUCTURE_HEALTH_STATUS_STALE
                severity = "warning"
                stale = True
                message = f"Source is stale. Latest successful activity is {age_seconds}s old."
            else:
                status = MARKET_STRUCTURE_HEALTH_STATUS_HEALTHY
                severity = "ok"
                stale = False
                message = "Source is healthy."
    return MarketStructureSourceHealthRead(
        status=status,
        severity=severity,
        ingest_mode=ingest_mode,
        stale=stale,
        stale_after_seconds=stale_after_seconds,
        last_activity_at=last_activity_at,
        last_success_at=last_success_at,
        last_snapshot_at=last_snapshot_at,
        last_error=source.last_error,
        health_changed_at=source.health_changed_at,
        consecutive_failures=consecutive_failures,
        backoff_until=backoff_until,
        backoff_active=backoff_active,
        quarantined=quarantined,
        quarantined_at=source.quarantined_at,
        quarantine_reason=source.quarantine_reason,
        last_alerted_at=source.last_alerted_at,
        last_alert_kind=source.last_alert_kind,
        message=message,
    )


def clear_market_structure_failure_state(source) -> None:
    source.consecutive_failures = 0
    source.backoff_until = None


def mark_market_structure_poll_failure(source, *, error_message: str, now) -> None:
    failure_count = int(source.consecutive_failures or 0) + 1
    source.last_error = str(error_message)[:255]
    source.consecutive_failures = failure_count

    quarantine_after_failures = market_structure_quarantine_after_failures()
    if quarantine_after_failures > 0 and failure_count >= quarantine_after_failures:
        source.enabled = False
        source.backoff_until = None
        source.quarantined_at = ensure_utc(now)
        source.quarantine_reason = (
            f"Source entered quarantine after {failure_count} consecutive polling failures: {source.last_error}"
        )[:255]
        return

    backoff_seconds = market_structure_backoff_seconds_for_failure_count(failure_count)
    if backoff_seconds > 0:
        source.backoff_until = ensure_utc(now) + timedelta(seconds=backoff_seconds)
    else:
        source.backoff_until = None


def mark_market_structure_source_success(source, *, now, latest_snapshot_at) -> None:
    source.last_success_at = ensure_utc(now)
    if latest_snapshot_at is not None:
        source.last_snapshot_at = latest_snapshot_at
    source.last_error = None
    clear_market_structure_failure_state(source)


def sync_market_structure_source_health_fields(source, *, now) -> bool:
    health = build_market_structure_source_health(source, now=now)
    changed = source.health_status != health.status
    source.health_status = health.status
    if changed or source.health_changed_at is None:
        source.health_changed_at = ensure_utc(now)
    return changed


def next_market_structure_alert_kind(previous_health_status: str | None, current_health_status: str) -> str | None:
    if current_health_status == MARKET_STRUCTURE_HEALTH_STATUS_QUARANTINED:
        return (
            MARKET_STRUCTURE_ALERT_KIND_QUARANTINED
            if previous_health_status != MARKET_STRUCTURE_HEALTH_STATUS_QUARANTINED
            else None
        )
    if current_health_status == MARKET_STRUCTURE_HEALTH_STATUS_ERROR:
        return (
            MARKET_STRUCTURE_ALERT_KIND_ERROR if previous_health_status != MARKET_STRUCTURE_HEALTH_STATUS_ERROR else None
        )
    if current_health_status == MARKET_STRUCTURE_HEALTH_STATUS_STALE:
        return (
            MARKET_STRUCTURE_ALERT_KIND_STALE if previous_health_status != MARKET_STRUCTURE_HEALTH_STATUS_STALE else None
        )
    return None


def apply_market_structure_alert_transition(
    source,
    *,
    previous_health_status: str | None,
    now,
) -> str | None:
    alert_kind = next_market_structure_alert_kind(
        previous_health_status,
        build_market_structure_source_health(source, now=now).status,
    )
    if alert_kind is None:
        return None
    source.last_alert_kind = alert_kind
    source.last_alerted_at = ensure_utc(now)
    return alert_kind


def market_structure_source_health_event_payload(source, *, now) -> dict[str, object]:
    health = build_market_structure_source_health(source, now=now)
    return {
        "timestamp": ensure_utc(now),
        "source_id": int(source.id),
        "plugin_name": source.plugin_name,
        "display_name": source.display_name,
        "enabled": bool(source.enabled),
        "auth_mode": source.auth_mode,
        "health_status": health.status,
        "health_severity": health.severity,
        "ingest_mode": health.ingest_mode,
        "stale": bool(health.stale),
        "stale_after_seconds": health.stale_after_seconds,
        "last_activity_at": isoformat_or_none(health.last_activity_at),
        "last_success_at": isoformat_or_none(health.last_success_at),
        "last_snapshot_at": isoformat_or_none(health.last_snapshot_at),
        "last_error": health.last_error,
        "health_changed_at": isoformat_or_none(health.health_changed_at),
        "consecutive_failures": int(health.consecutive_failures),
        "backoff_until": isoformat_or_none(health.backoff_until),
        "backoff_active": bool(health.backoff_active),
        "quarantined": bool(health.quarantined),
        "quarantined_at": isoformat_or_none(health.quarantined_at),
        "quarantine_reason": health.quarantine_reason,
        "last_alerted_at": isoformat_or_none(health.last_alerted_at),
        "last_alert_kind": health.last_alert_kind,
        "message": health.message,
    }


def market_structure_source_alert_event_payload(source, *, alert_kind: str, now) -> dict[str, object]:
    health = build_market_structure_source_health(source, now=now)
    rule = {
        MARKET_STRUCTURE_ALERT_KIND_ERROR: "poll_failure_detected",
        MARKET_STRUCTURE_ALERT_KIND_STALE: "source_stale_detected",
        MARKET_STRUCTURE_ALERT_KIND_QUARANTINED: "poll_failure_quarantine_triggered",
    }[alert_kind]
    recommended_action = {
        MARKET_STRUCTURE_ALERT_KIND_ERROR: "Allow backoff to retry or inspect source credentials and upstream API health.",
        MARKET_STRUCTURE_ALERT_KIND_STALE: "Inspect upstream collector latency and recent snapshot ingestion flow.",
        MARKET_STRUCTURE_ALERT_KIND_QUARANTINED: "Review the source, clear the error, release quarantine, then re-enable polling.",
    }[alert_kind]
    return {
        **market_structure_source_health_event_payload(source, now=now),
        "alert_kind": alert_kind,
        "rule": rule,
        "recommended_action": recommended_action,
        "severity": health.severity,
    }


__all__ = [
    "apply_market_structure_alert_transition",
    "build_market_structure_source_health",
    "clear_market_structure_failure_state",
    "isoformat_or_none",
    "mark_market_structure_poll_failure",
    "mark_market_structure_source_success",
    "market_structure_backoff_active",
    "market_structure_credential_fields_present",
    "market_structure_is_quarantined",
    "market_structure_source_alert_event_payload",
    "market_structure_source_health_event_payload",
    "market_structure_source_ingest_mode",
    "market_structure_source_provider",
    "market_structure_source_status",
    "market_structure_stale_after_seconds",
    "merge_market_structure_mapping",
    "sync_market_structure_source_health_fields",
]
