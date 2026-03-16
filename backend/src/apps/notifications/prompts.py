from src.apps.notifications.constants import (
    PROMPT_TASK_NOTIFICATION_HUMANIZE,
)
from src.core.ai.contracts import AICapability
from src.core.ai.prompt_policy import (
    PromptTaskPolicy,
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

def _register_notification_prompts() -> None:
    register_prompt_task_policy(
        PromptTaskPolicy(
            capability=AICapability.NOTIFICATION_HUMANIZE,
            task=PROMPT_TASK_NOTIFICATION_HUMANIZE,
            schema_contract=NOTIFICATION_OUTPUT_SCHEMA,
        )
    )


_register_notification_prompts()


__all__ = ["NOTIFICATION_OUTPUT_SCHEMA"]
