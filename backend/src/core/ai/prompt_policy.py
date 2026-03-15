from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.ai.contracts import AICapability


@dataclass(frozen=True, slots=True)
class PromptTaskPolicy:
    capability: AICapability
    task: str
    editable: bool
    schema_contract: dict[str, Any] | str


@dataclass(frozen=True, slots=True)
class BuiltinPromptDefinition:
    capability: AICapability
    task: str
    name: str
    version: int
    template: str
    vars_json: dict[str, Any]
    schema_contract: dict[str, Any] | str
    style_profile: str | None
    editable: bool
    source: str


_TASK_POLICIES: dict[str, PromptTaskPolicy] = {}
_BUILTIN_PROMPTS: dict[tuple[str, int, str], BuiltinPromptDefinition] = {}


def register_prompt_task_policy(policy: PromptTaskPolicy) -> None:
    task = str(policy.task).strip()
    if not task:
        raise ValueError("Prompt task policy requires a non-empty task name.")
    _TASK_POLICIES[task] = PromptTaskPolicy(
        capability=policy.capability,
        task=task,
        editable=bool(policy.editable),
        schema_contract=policy.schema_contract,
    )


def register_builtin_prompt_definition(definition: BuiltinPromptDefinition) -> None:
    name = str(definition.name).strip()
    if not name:
        raise ValueError("Builtin prompt definition requires a non-empty name.")
    key = (name, int(definition.version), str(definition.source).strip() or "code")
    _BUILTIN_PROMPTS[key] = BuiltinPromptDefinition(
        capability=definition.capability,
        task=str(definition.task).strip(),
        name=name,
        version=int(definition.version),
        template=str(definition.template),
        vars_json=dict(definition.vars_json),
        schema_contract=definition.schema_contract,
        style_profile=definition.style_profile,
        editable=bool(definition.editable),
        source=key[2],
    )


def register_builtin_prompt_definitions(definitions: tuple[BuiltinPromptDefinition, ...] | list[BuiltinPromptDefinition]) -> None:
    for definition in definitions:
        register_builtin_prompt_definition(definition)


def get_prompt_task_policy(task: str) -> PromptTaskPolicy | None:
    return _TASK_POLICIES.get(str(task).strip())


def prompt_style_profile(vars_json: dict[str, Any] | None) -> str | None:
    raw = None if vars_json is None else vars_json.get("style_profile")
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def list_builtin_prompt_definitions() -> tuple[BuiltinPromptDefinition, ...]:
    return tuple(sorted(_BUILTIN_PROMPTS.values(), key=lambda item: (item.capability.value, item.name, item.version)))


__all__ = [
    "BuiltinPromptDefinition",
    "PromptTaskPolicy",
    "get_prompt_task_policy",
    "list_builtin_prompt_definitions",
    "prompt_style_profile",
    "register_builtin_prompt_definition",
    "register_builtin_prompt_definitions",
    "register_prompt_task_policy",
]
