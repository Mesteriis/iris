from __future__ import annotations

from src.core.ai.contracts import AICapability
from src.core.ai.prompt_policy import (
    PromptTaskPolicy,
    register_prompt_task_policy,
)

PROMPT_TASK_BRIEF_GENERATE = "brief_generate"

BRIEF_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["title", "summary", "bullets"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "bullets": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 5,
        },
    },
    "additionalProperties": False,
}

def _register_brief_prompts() -> None:
    register_prompt_task_policy(
        PromptTaskPolicy(
            capability=AICapability.BRIEF_GENERATE,
            task=PROMPT_TASK_BRIEF_GENERATE,
            schema_contract=BRIEF_OUTPUT_SCHEMA,
        )
    )


_register_brief_prompts()


__all__ = [
    "BRIEF_OUTPUT_SCHEMA",
    "PROMPT_TASK_BRIEF_GENERATE",
]
