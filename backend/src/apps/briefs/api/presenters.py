from __future__ import annotations

from typing import Any

from src.apps.briefs.api.contracts import BriefJobAcceptedRead, BriefRead
from src.apps.briefs.contracts import BriefKind
from src.core.db.persistence import thaw_json_value
from src.core.http.analytics import analytical_metadata
from src.core.http.operation_store import OperationDispatchResult


def brief_read(item: Any) -> BriefRead:
    payload = {
        "id": int(item.id),
        "brief_kind": item.brief_kind,
        "scope_key": item.scope_key,
        "symbol": item.symbol,
        "coin_id": item.coin_id,
        "language": item.language,
        "title": item.title,
        "summary": item.summary,
        "bullets": list(item.bullets),
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
    language: str,
    symbol: str | None = None,
) -> BriefJobAcceptedRead:
    operation = dispatch_result.operation
    return BriefJobAcceptedRead.model_validate(
        {
            "operation_id": operation.operation_id,
            "accepted_at": operation.accepted_at,
            "correlation_id": operation.correlation_id,
            "deduplicated": dispatch_result.deduplicated,
            "message": dispatch_result.message,
            "brief_kind": brief_kind,
            "scope_key": scope_key,
            "language": language,
            "symbol": symbol,
        }
    )


__all__ = ["brief_job_accepted_read", "brief_read"]
