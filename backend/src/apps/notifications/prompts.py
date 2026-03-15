from __future__ import annotations

from dataclasses import dataclass

from src.apps.notifications.constants import (
    DEFAULT_NOTIFICATION_PROMPT_NAME,
    DEFAULT_NOTIFICATION_PROMPT_VERSION,
    EVENT_PROMPT_NAMES,
    PROMPT_TASK_NOTIFICATION_HUMANIZE,
    SUPPORTED_NOTIFICATION_SOURCE_EVENTS,
)
from src.core.ai.contracts import AICapability
from src.core.ai.prompt_policy import (
    BuiltinPromptDefinition,
    PromptTaskPolicy,
    prompt_style_profile,
    register_builtin_prompt_definitions,
    register_prompt_task_policy,
)

NOTIFICATION_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["title", "message", "severity", "urgency"],
    "properties": {
        "title": {"type": "string"},
        "message": {"type": "string"},
        "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
        "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "additionalProperties": False,
}

_BASE_TEMPLATE = """
You produce a short investor-facing notification from a canonical IRIS event.

Rules:
- Return valid JSON only.
- Keep the title short and specific.
- Keep the message concise, factual and grounded in the provided canonical fields.
- Do not invent prices, causes or recommendations that are absent from the context.
- Mention the symbol when it is available.
- Use the effective language exactly as requested by the execution contract.
- Map urgency and severity to the business importance of the event.
""".strip()

_EVENT_TEMPLATE_SUFFIXES: dict[str, str] = {
    "signal_created": "Explain the signal in plain language without pretending it is a confirmed outcome.",
    "anomaly_detected": "Treat anomalies as cautionary events and avoid overclaiming certainty.",
    "decision_generated": "Present the decision as a generated action candidate, not as executed trade confirmation.",
    "market_regime_changed": "Emphasize the regime transition and its practical meaning for a passive investor.",
    "portfolio_position_changed": "Describe the portfolio position change as an observed state update.",
    "portfolio_balance_updated": "Describe the balance update as a sync result and keep the wording operational.",
}


@dataclass(frozen=True, slots=True)
class NotificationPrompt:
    name: str
    task: str
    version: int
    template: str
    vars_json: dict[str, object]


def load_notification_prompt(event_type: str) -> NotificationPrompt:
    prompt_name = EVENT_PROMPT_NAMES.get(event_type, DEFAULT_NOTIFICATION_PROMPT_NAME)
    suffix = _EVENT_TEMPLATE_SUFFIXES.get(event_type, "Keep the narration grounded in the canonical event.")
    return NotificationPrompt(
        name=prompt_name,
        task=PROMPT_TASK_NOTIFICATION_HUMANIZE,
        version=DEFAULT_NOTIFICATION_PROMPT_VERSION,
        template=f"{_BASE_TEMPLATE}\n\nEvent-specific guidance:\n- {suffix}",
        vars_json={
            "style_profile": "calm_investor_alert",
            "max_title_chars": 96,
            "max_message_chars": 280,
        },
    )


def _register_notification_prompts() -> None:
    register_prompt_task_policy(
        PromptTaskPolicy(
            capability=AICapability.NOTIFICATION_HUMANIZE,
            task=PROMPT_TASK_NOTIFICATION_HUMANIZE,
            editable=False,
            schema_contract=NOTIFICATION_OUTPUT_SCHEMA,
        )
    )
    prompts_by_name = {"default": load_notification_prompt("")}
    for event_type in sorted(SUPPORTED_NOTIFICATION_SOURCE_EVENTS):
        prompt = load_notification_prompt(event_type)
        prompts_by_name[prompt.name] = prompt
    register_builtin_prompt_definitions(
        [
            BuiltinPromptDefinition(
                capability=AICapability.NOTIFICATION_HUMANIZE,
                task=prompt.task,
                name=prompt.name,
                version=prompt.version,
                template=prompt.template,
                vars_json=dict(prompt.vars_json),
                schema_contract=NOTIFICATION_OUTPUT_SCHEMA,
                style_profile=prompt_style_profile(prompt.vars_json),
                editable=False,
                source="code",
            )
            for prompt in prompts_by_name.values()
        ]
    )


_register_notification_prompts()


__all__ = ["NOTIFICATION_OUTPUT_SCHEMA", "NotificationPrompt", "load_notification_prompt"]
