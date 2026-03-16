from typing import Any

from src.apps.briefs.api.contracts import BriefJobAcceptedRead, BriefRead
from src.apps.briefs.contracts import BriefKind
from src.core.db.persistence import thaw_json_value
from src.core.http.analytics import analytical_metadata
from src.core.http.operation_localization import dispatch_result_message_fields
from src.core.http.operation_store import OperationDispatchResult
from src.core.i18n import (
    CONTENT_KIND_GENERATED_TEXT,
    ContentPayloadValidationError,
    content_kind,
    content_rendered_locale,
    content_text,
    content_text_list,
    validate_content_payload,
)


def brief_read(item: Any) -> BriefRead:
    raw_content_json = thaw_json_value(item.content_json)
    try:
        content_json = validate_content_payload(raw_content_json)
    except ContentPayloadValidationError:
        content_json = {}
    resolved_content_kind = content_kind(content_json) or CONTENT_KIND_GENERATED_TEXT
    payload = {
        "id": int(item.id),
        "brief_kind": item.brief_kind,
        "scope_key": item.scope_key,
        "symbol": item.symbol,
        "coin_id": item.coin_id,
        "content_kind": resolved_content_kind,
        "rendered_locale": content_rendered_locale(content_json),
        "title": content_text(content_json, "title") or "",
        "summary": content_text(content_json, "summary") or "",
        "bullets": content_text_list(content_json, "bullets"),
        "content_json": content_json,
        "refs_json": thaw_json_value(item.refs_json),
        "context_json": thaw_json_value(item.context_json),
        "provider": item.provider,
        "model": item.model,
        "prompt_name": item.prompt_name,
        "prompt_version": int(item.prompt_version),
        "source_updated_at": item.source_updated_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
    return BriefRead.model_validate(
        {
            **payload,
            **analytical_metadata(
                source_updated_at=item.source_updated_at,
                consistency="derived",
                freshness_class="near_real_time",
                generated_at=item.updated_at,
            ),
        }
    )


def brief_job_accepted_read(
    *,
    dispatch_result: OperationDispatchResult,
    brief_kind: BriefKind,
    scope_key: str,
    rendered_locale: str,
    symbol: str | None = None,
    locale: str | None = None,
) -> BriefJobAcceptedRead:
    operation = dispatch_result.operation
    return BriefJobAcceptedRead.model_validate(
        {
            "operation_id": operation.operation_id,
            "accepted_at": operation.accepted_at,
            "correlation_id": operation.correlation_id,
            "deduplicated": dispatch_result.deduplicated,
            **dispatch_result_message_fields(dispatch_result, locale=locale),
            "brief_kind": brief_kind,
            "scope_key": scope_key,
            "rendered_locale": rendered_locale,
            "symbol": symbol,
        }
    )


__all__ = ["brief_job_accepted_read", "brief_read"]
