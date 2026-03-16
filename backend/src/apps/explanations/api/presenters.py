from typing import Any

from src.apps.explanations.api.contracts import ExplanationJobAcceptedRead, ExplanationRead
from src.apps.explanations.contracts import ExplainKind
from src.core.db.persistence import thaw_json_value
from src.core.http.analytics import analytical_metadata
from src.core.http.operation_localization import dispatch_result_message_fields
from src.core.http.operation_store import OperationDispatchResult
from src.core.i18n import (
    CONTENT_KIND_DESCRIPTOR_BUNDLE,
    CONTENT_KIND_GENERATED_TEXT,
    ContentPayloadValidationError,
    content_descriptor,
    content_descriptors,
    content_kind,
    content_rendered_locale,
    content_text,
    content_text_list,
    is_descriptor_bundle_content,
    is_generated_text_content,
    load_message_descriptor,
    load_message_descriptors,
    localize_message_descriptor,
    validate_content_payload,
)


def explanation_read(item: Any, *, locale: str | None = None) -> ExplanationRead:
    raw_content_json = thaw_json_value(item.content_json)
    try:
        content_json = validate_content_payload(raw_content_json)
    except ContentPayloadValidationError:
        content_json = {}
    context_json = thaw_json_value(item.context_json)
    title_descriptor = None
    explanation_descriptor = None
    bullet_descriptors: tuple = ()
    title = None
    explanation = None
    bullets: list[str] = []
    effective_locale = None
    resolved_content_kind = content_kind(content_json)

    if is_descriptor_bundle_content(content_json):
        title_descriptor = content_descriptor(content_json, "title")
        explanation_descriptor = content_descriptor(content_json, "explanation")
        bullet_descriptors = content_descriptors(content_json, "bullets")
        title, localized_locale = localize_message_descriptor(title_descriptor, locale=locale)
        explanation, explanation_locale = localize_message_descriptor(explanation_descriptor, locale=locale)
        bullets = [
            localize_message_descriptor(descriptor, locale=locale)[0] or ""
            for descriptor in bullet_descriptors
        ]
        effective_locale = localized_locale or explanation_locale
    elif is_generated_text_content(content_json):
        title = content_text(content_json, "title")
        explanation = content_text(content_json, "explanation")
        bullets = content_text_list(content_json, "bullets")
        effective_locale = content_rendered_locale(content_json)
    else:
        localization = context_json.get("localization") if isinstance(context_json, dict) else None
        title_descriptor = load_message_descriptor(localization.get("title")) if isinstance(localization, dict) else None
        explanation_descriptor = load_message_descriptor(localization.get("explanation")) if isinstance(localization, dict) else None
        bullet_descriptors = load_message_descriptors(localization.get("bullets")) if isinstance(localization, dict) else ()
        title, localized_locale = localize_message_descriptor(title_descriptor, locale=locale)
        explanation, explanation_locale = localize_message_descriptor(explanation_descriptor, locale=locale)
        if bullet_descriptors:
            bullets = [
                localize_message_descriptor(descriptor, locale=locale)[0] or ""
                for descriptor in bullet_descriptors
            ]
        else:
            bullets = list(item.bullets)
        effective_locale = localized_locale or explanation_locale
        if title_descriptor is not None or explanation_descriptor is not None or bullet_descriptors:
            resolved_content_kind = CONTENT_KIND_DESCRIPTOR_BUNDLE
        else:
            resolved_content_kind = CONTENT_KIND_GENERATED_TEXT

    payload = {
        "id": int(item.id),
        "explain_kind": item.explain_kind,
        "subject_id": int(item.subject_id),
        "coin_id": item.coin_id,
        "symbol": item.symbol,
        "timeframe": item.timeframe,
        "title": title or "",
        "content_kind": resolved_content_kind or CONTENT_KIND_GENERATED_TEXT,
        "rendered_locale": effective_locale,
        "title_key": title_descriptor.key if title_descriptor is not None else None,
        "title_params": dict(title_descriptor.params) if title_descriptor is not None else {},
        "explanation": explanation or "",
        "explanation_key": explanation_descriptor.key if explanation_descriptor is not None else None,
        "explanation_params": dict(explanation_descriptor.params) if explanation_descriptor is not None else {},
        "bullets": bullets,
        "bullet_keys": [descriptor.key for descriptor in bullet_descriptors],
        "bullet_params": [dict(descriptor.params) for descriptor in bullet_descriptors],
        "content_json": content_json,
        "refs_json": thaw_json_value(item.refs_json),
        "context_json": context_json,
        "provider": item.provider,
        "model": item.model,
        "prompt_name": item.prompt_name,
        "prompt_version": int(item.prompt_version),
        "subject_updated_at": item.subject_updated_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
    return ExplanationRead.model_validate(
        {
            **payload,
            **analytical_metadata(
                source_updated_at=item.subject_updated_at,
                consistency="derived",
                freshness_class="near_real_time",
                generated_at=item.updated_at,
            ),
        }
    )


def explanation_job_accepted_read(
    *,
    dispatch_result: OperationDispatchResult,
    explain_kind: ExplainKind,
    subject_id: int,
    rendered_locale: str,
    symbol: str | None = None,
    timeframe: int | None = None,
    locale: str | None = None,
) -> ExplanationJobAcceptedRead:
    operation = dispatch_result.operation
    return ExplanationJobAcceptedRead.model_validate(
        {
            "operation_id": operation.operation_id,
            "accepted_at": operation.accepted_at,
            "correlation_id": operation.correlation_id,
            "deduplicated": dispatch_result.deduplicated,
            **dispatch_result_message_fields(dispatch_result, locale=locale),
            "explain_kind": explain_kind,
            "subject_id": int(subject_id),
            "rendered_locale": rendered_locale,
            "symbol": symbol,
            "timeframe": timeframe,
        }
    )


__all__ = ["explanation_job_accepted_read", "explanation_read"]
