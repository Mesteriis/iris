from typing import Literal

from src.apps.hypothesis_engine.schemas import (
    AIHypothesisEvalRead,
    AIHypothesisRead,
    AIPromptCreate,
    AIPromptRead,
    AIPromptUpdate,
)
from src.core.http.contracts import AcceptedResponse


class HypothesisEvaluationJobAcceptedRead(AcceptedResponse):
    operation_type: Literal["hypothesis.evaluate"] = "hypothesis.evaluate"


__all__ = [
    "AIHypothesisEvalRead",
    "AIHypothesisRead",
    "AIPromptCreate",
    "AIPromptRead",
    "AIPromptUpdate",
    "HypothesisEvaluationJobAcceptedRead",
]
