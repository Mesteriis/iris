from typing import Any

from src.apps.hypothesis_engine.api.contracts import (
    AIHypothesisEvalRead,
    AIHypothesisRead,
    AIPromptRead,
    HypothesisEvaluationJobAcceptedRead,
)
from src.core.http.operation_localization import dispatch_result_message_fields
from src.core.http.operation_store import OperationDispatchResult


def prompt_read(item: Any) -> AIPromptRead:
    source = getattr(item, "prompt", item)
    return AIPromptRead.model_validate(source)


def hypothesis_read(item: Any) -> AIHypothesisRead:
    return AIHypothesisRead.model_validate(item)


def hypothesis_eval_read(item: Any) -> AIHypothesisEvalRead:
    return AIHypothesisEvalRead.model_validate(item)


def hypothesis_evaluation_job_accepted_read(
    *,
    dispatch_result: OperationDispatchResult,
    locale: str | None = None,
) -> HypothesisEvaluationJobAcceptedRead:
    operation = dispatch_result.operation
    return HypothesisEvaluationJobAcceptedRead.model_validate(
        {
            "operation_id": operation.operation_id,
            "accepted_at": operation.accepted_at,
            "correlation_id": operation.correlation_id,
            "deduplicated": dispatch_result.deduplicated,
            **dispatch_result_message_fields(dispatch_result, locale=locale),
        }
    )


__all__ = [
    "hypothesis_eval_read",
    "hypothesis_evaluation_job_accepted_read",
    "hypothesis_read",
    "prompt_read",
]
