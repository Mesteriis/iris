from __future__ import annotations

from typing import Any

from src.apps.hypothesis_engine.api.contracts import (
    AIHypothesisEvalRead,
    AIHypothesisRead,
    AIPromptRead,
    HypothesisEvaluationJobAcceptedRead,
)
from src.core.http.responses import accepted


def prompt_read(item: Any) -> AIPromptRead:
    return AIPromptRead.model_validate(item)


def hypothesis_read(item: Any) -> AIHypothesisRead:
    return AIHypothesisRead.model_validate(item)


def hypothesis_eval_read(item: Any) -> AIHypothesisEvalRead:
    return AIHypothesisEvalRead.model_validate(item)


def hypothesis_evaluation_job_accepted_read() -> HypothesisEvaluationJobAcceptedRead:
    return HypothesisEvaluationJobAcceptedRead.model_validate(
        accepted(
            operation_type="hypothesis.evaluate",
            message="Hypothesis evaluation job queued.",
        ).model_dump(mode="json")
    )


__all__ = [
    "hypothesis_eval_read",
    "hypothesis_evaluation_job_accepted_read",
    "hypothesis_read",
    "prompt_read",
]
