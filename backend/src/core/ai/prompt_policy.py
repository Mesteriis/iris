from dataclasses import dataclass
from typing import Any

from src.core.ai.contracts import AICapability


@dataclass(frozen=True, slots=True)
class PromptTaskPolicy:
    capability: AICapability
    task: str
    schema_contract: dict[str, Any] | str


_TASK_POLICIES: dict[str, PromptTaskPolicy] = {}


def register_prompt_task_policy(policy: PromptTaskPolicy) -> None:
    task = str(policy.task).strip()
    if not task:
        raise ValueError("Prompt task policy requires a non-empty task name.")
    _TASK_POLICIES[task] = PromptTaskPolicy(
        capability=policy.capability,
        task=task,
        schema_contract=policy.schema_contract,
    )


def get_prompt_task_policy(task: str) -> PromptTaskPolicy | None:
    return _TASK_POLICIES.get(str(task).strip())


def prompt_style_profile(vars_json: dict[str, Any] | None) -> str | None:
    raw = None if vars_json is None else vars_json.get("style_profile")
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


__all__ = [
    "PromptTaskPolicy",
    "get_prompt_task_policy",
    "prompt_style_profile",
    "register_prompt_task_policy",
]
