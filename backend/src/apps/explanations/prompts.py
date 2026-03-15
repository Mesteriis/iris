from __future__ import annotations

from src.core.ai.contracts import AICapability
from src.core.ai.prompt_policy import (
    PromptTaskPolicy,
    register_prompt_task_policy,
)

PROMPT_TASK_EXPLAIN_GENERATE = "explain_generate"

EXPLAIN_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["title", "explanation", "bullets"],
    "properties": {
        "title": {"type": "string"},
        "explanation": {"type": "string"},
        "bullets": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 5,
        },
    },
    "additionalProperties": False,
}

def _register_explanation_prompts() -> None:
    register_prompt_task_policy(
        PromptTaskPolicy(
            capability=AICapability.EXPLAIN_GENERATE,
            task=PROMPT_TASK_EXPLAIN_GENERATE,
            schema_contract=EXPLAIN_OUTPUT_SCHEMA,
        )
    )


_register_explanation_prompts()


__all__ = [
    "EXPLAIN_OUTPUT_SCHEMA",
    "PROMPT_TASK_EXPLAIN_GENERATE",
]
