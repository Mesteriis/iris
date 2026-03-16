from typing import Any

from iris.apps.notifications.api.contracts import NotificationRead
from iris.core.db.persistence import thaw_json_value
from iris.core.i18n import (
    CONTENT_KIND_DESCRIPTOR_BUNDLE,
    CONTENT_KIND_GENERATED_TEXT,
    ContentPayloadValidationError,
    content_descriptor,
    content_kind,
    content_rendered_locale,
    content_text,
    is_descriptor_bundle_content,
    is_generated_text_content,
    load_message_descriptor,
    localize_message_descriptor,
    validate_content_payload,
)


def notification_read(item: Any, *, locale: str | None = None) -> NotificationRead:
    raw_content_json = thaw_json_value(item.content_json)
    try:
        content_json = validate_content_payload(raw_content_json)
    except ContentPayloadValidationError:
        content_json = {}
    context_json = thaw_json_value(item.context_json)
    title_descriptor = None
    message_descriptor = None
    title = None
    message = None
    effective_locale = None
    resolved_content_kind = content_kind(content_json)

    if is_descriptor_bundle_content(content_json):
        title_descriptor = content_descriptor(content_json, "title")
        message_descriptor = content_descriptor(content_json, "message")
        title, localized_locale = localize_message_descriptor(title_descriptor, locale=locale)
        message, message_locale = localize_message_descriptor(message_descriptor, locale=locale)
        effective_locale = localized_locale or message_locale
    elif is_generated_text_content(content_json):
        title = content_text(content_json, "title")
        message = content_text(content_json, "message")
        effective_locale = content_rendered_locale(content_json)
    else:
        localization = context_json.get("localization") if isinstance(context_json, dict) else None
        title_descriptor = load_message_descriptor(localization.get("title")) if isinstance(localization, dict) else None
        message_descriptor = load_message_descriptor(localization.get("message")) if isinstance(localization, dict) else None
        title, localized_locale = localize_message_descriptor(title_descriptor, locale=locale)
        message, message_locale = localize_message_descriptor(message_descriptor, locale=locale)
        effective_locale = localized_locale or message_locale
        if title_descriptor is not None or message_descriptor is not None:
            resolved_content_kind = CONTENT_KIND_DESCRIPTOR_BUNDLE
        else:
            resolved_content_kind = CONTENT_KIND_GENERATED_TEXT

    return NotificationRead.model_validate(
        {
            "id": int(item.id),
            "coin_id": int(item.coin_id),
            "symbol": item.symbol,
            "sector": item.sector,
            "timeframe": int(item.timeframe),
            "title": title or "",
            "content_kind": resolved_content_kind or CONTENT_KIND_GENERATED_TEXT,
            "rendered_locale": effective_locale,
            "title_key": title_descriptor.key if title_descriptor is not None else None,
            "title_params": dict(title_descriptor.params) if title_descriptor is not None else {},
            "message": message or "",
            "message_key": message_descriptor.key if message_descriptor is not None else None,
            "message_params": dict(message_descriptor.params) if message_descriptor is not None else {},
            "severity": item.severity,
            "urgency": item.urgency,
            "content_json": content_json,
            "refs_json": thaw_json_value(item.refs_json),
            "context_json": context_json,
            "provider": item.provider,
            "model": item.model,
            "prompt_name": item.prompt_name,
            "prompt_version": int(item.prompt_version),
            "source_event_type": item.source_event_type,
            "source_event_id": item.source_event_id,
            "source_stream_id": item.source_stream_id,
            "causation_id": item.causation_id,
            "correlation_id": item.correlation_id,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
    )


__all__ = ["notification_read"]
