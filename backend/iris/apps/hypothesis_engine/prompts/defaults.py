from typing import Any

from iris.apps.hypothesis_engine.constants import (
    PROMPT_TASK_HYPOTHESIS_GENERATION,
)
from iris.core.ai.contracts import AICapability
from iris.core.ai.prompt_policy import (
    PromptTaskPolicy,
    register_prompt_task_policy,
)

HYPOTHESIS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "confidence", "horizon_min", "direction", "target_move", "summary", "assets"],
    "properties": {
        "type": {"type": "string"},
        "confidence": {"type": "number"},
        "horizon_min": {"type": "integer"},
        "direction": {"type": "string", "enum": ["up", "down", "neutral"]},
        "target_move": {"type": "number"},
        "summary": {"type": "string"},
        "assets": {"type": "array", "items": {"type": "string"}},
        "explain": {"type": "string"},
        "kind": {"type": "string"},
    },
}

def _register_hypothesis_prompt_defaults() -> None:
    register_prompt_task_policy(
        PromptTaskPolicy(
            capability=AICapability.HYPOTHESIS_GENERATE,
            task=PROMPT_TASK_HYPOTHESIS_GENERATION,
            schema_contract=HYPOTHESIS_OUTPUT_SCHEMA,
        )
    )


_register_hypothesis_prompt_defaults()
