from __future__ import annotations

from typing import Any

from src.apps.explanations.api.contracts import ExplanationJobAcceptedRead, ExplanationRead
from src.apps.explanations.contracts import ExplainKind
from src.core.db.persistence import thaw_json_value
from src.core.http.analytics import analytical_metadata
from src.core.http.operation_store import OperationDispatchResult


def explanation_read(item: Any) -> ExplanationRead:
    payload = {
        "id": int(item.id),
        "explain_kind": item.explain_kind,
        "subject_id": int(item.subject_id),
        "coin_id": item.coin_id,
        "symbol": item.symbol,
        "timeframe": item.timeframe,
        "language": item.language,
        "title": item.title,
        "explanation": item.explanation,
        "bullets": list(item.bullets),
        "refs_json": thaw_json_value(item.refs_json),
        "context_json": thaw_json_value(item.context_json),
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
    language: str,
    symbol: str | None = None,
    timeframe: int | None = None,
) -> ExplanationJobAcceptedRead:
    operation = dispatch_result.operation
    return ExplanationJobAcceptedRead.model_validate(
        {
            "operation_id": operation.operation_id,
            "accepted_at": operation.accepted_at,
            "correlation_id": operation.correlation_id,
            "deduplicated": dispatch_result.deduplicated,
            "message": dispatch_result.message,
            "explain_kind": explain_kind,
            "subject_id": int(subject_id),
            "language": language,
            "symbol": symbol,
            "timeframe": timeframe,
        }
    )


__all__ = ["explanation_job_accepted_read", "explanation_read"]
