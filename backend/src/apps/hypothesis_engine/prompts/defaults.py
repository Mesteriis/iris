from __future__ import annotations

from typing import Any

from src.apps.hypothesis_engine.constants import (
    DEFAULT_HYPOTHESIS_HORIZON_MIN,
    DEFAULT_PROMPT_NAME,
    DEFAULT_PROMPT_VERSION,
    DEFAULT_TARGET_MOVE,
    EVENT_PROMPT_NAMES,
    PROMPT_TASK_HYPOTHESIS_GENERATION,
)
from src.core.ai.contracts import AICapability
from src.core.ai.prompt_policy import (
    BuiltinPromptDefinition,
    PromptTaskPolicy,
    prompt_style_profile,
    register_builtin_prompt_definitions,
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

_DEFAULT_TEMPLATE = (
    "You are IRIS hypothesis engine. Produce one testable market hypothesis as JSON only. "
    "Focus on the triggering event, specify direction, horizon, target move, summary, and assets."
)


def _fallback_vars() -> dict[str, Any]:
    return {
        "horizon_min": DEFAULT_HYPOTHESIS_HORIZON_MIN,
        "target_move": DEFAULT_TARGET_MOVE,
        "style_profile": "default",
    }


DEFAULT_PROMPTS: dict[str, dict[str, Any]] = {
    DEFAULT_PROMPT_NAME: {
        "name": DEFAULT_PROMPT_NAME,
        "task": PROMPT_TASK_HYPOTHESIS_GENERATION,
        "version": DEFAULT_PROMPT_VERSION,
        "template": _DEFAULT_TEMPLATE,
        "vars_json": _fallback_vars(),
    }
}

for event_type, prompt_name in EVENT_PROMPT_NAMES.items():
    DEFAULT_PROMPTS[prompt_name] = {
        "name": prompt_name,
        "task": PROMPT_TASK_HYPOTHESIS_GENERATION,
        "version": DEFAULT_PROMPT_VERSION,
        "template": f"{_DEFAULT_TEMPLATE} Triggering event type: {event_type}.",
        "vars_json": _fallback_vars(),
    }


def get_fallback_prompt(name: str) -> dict[str, Any]:
    return dict(DEFAULT_PROMPTS.get(name, DEFAULT_PROMPTS[DEFAULT_PROMPT_NAME]))


def _register_hypothesis_prompt_defaults() -> None:
    register_prompt_task_policy(
        PromptTaskPolicy(
            capability=AICapability.HYPOTHESIS_GENERATE,
            task=PROMPT_TASK_HYPOTHESIS_GENERATION,
            editable=True,
            schema_contract=HYPOTHESIS_OUTPUT_SCHEMA,
        )
    )
    register_builtin_prompt_definitions(
        [
            BuiltinPromptDefinition(
                capability=AICapability.HYPOTHESIS_GENERATE,
                task=PROMPT_TASK_HYPOTHESIS_GENERATION,
                name=str(payload["name"]),
                version=int(payload["version"]),
                template=str(payload["template"]),
                vars_json=dict(payload.get("vars_json") or {}),
                schema_contract=HYPOTHESIS_OUTPUT_SCHEMA,
                style_profile=prompt_style_profile(dict(payload.get("vars_json") or {})),
                editable=True,
                source="fallback",
            )
            for payload in DEFAULT_PROMPTS.values()
        ]
    )


_register_hypothesis_prompt_defaults()
