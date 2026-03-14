from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.apps.briefs.contracts import BriefKind
from src.apps.briefs.prompts import BRIEF_OUTPUT_SCHEMA, PROMPT_TASK_BRIEF_GENERATE, load_brief_prompt
from src.apps.explanations.contracts import ExplainKind
from src.apps.explanations.prompts import EXPLAIN_OUTPUT_SCHEMA, PROMPT_TASK_EXPLAIN_GENERATE, load_explanation_prompt
from src.apps.hypothesis_engine.constants import PROMPT_TASK_HYPOTHESIS_GENERATION
from src.apps.hypothesis_engine.prompts.defaults import DEFAULT_PROMPTS, HYPOTHESIS_OUTPUT_SCHEMA
from src.apps.notifications.constants import PROMPT_TASK_NOTIFICATION_HUMANIZE, SUPPORTED_NOTIFICATION_SOURCE_EVENTS
from src.apps.notifications.prompts import NOTIFICATION_OUTPUT_SCHEMA, load_notification_prompt
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


_TASK_POLICIES: dict[str, PromptTaskPolicy] = {
    PROMPT_TASK_HYPOTHESIS_GENERATION: PromptTaskPolicy(
        capability=AICapability.HYPOTHESIS_GENERATE,
        task=PROMPT_TASK_HYPOTHESIS_GENERATION,
        editable=True,
        schema_contract=HYPOTHESIS_OUTPUT_SCHEMA,
    ),
    PROMPT_TASK_NOTIFICATION_HUMANIZE: PromptTaskPolicy(
        capability=AICapability.NOTIFICATION_HUMANIZE,
        task=PROMPT_TASK_NOTIFICATION_HUMANIZE,
        editable=False,
        schema_contract=NOTIFICATION_OUTPUT_SCHEMA,
    ),
    PROMPT_TASK_BRIEF_GENERATE: PromptTaskPolicy(
        capability=AICapability.BRIEF_GENERATE,
        task=PROMPT_TASK_BRIEF_GENERATE,
        editable=False,
        schema_contract=BRIEF_OUTPUT_SCHEMA,
    ),
    PROMPT_TASK_EXPLAIN_GENERATE: PromptTaskPolicy(
        capability=AICapability.EXPLAIN_GENERATE,
        task=PROMPT_TASK_EXPLAIN_GENERATE,
        editable=False,
        schema_contract=EXPLAIN_OUTPUT_SCHEMA,
    ),
}


def get_prompt_task_policy(task: str) -> PromptTaskPolicy | None:
    return _TASK_POLICIES.get(str(task).strip())


def prompt_style_profile(vars_json: dict[str, Any] | None) -> str | None:
    raw = None if vars_json is None else vars_json.get("style_profile")
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def list_builtin_prompt_definitions() -> tuple[BuiltinPromptDefinition, ...]:
    definitions: list[BuiltinPromptDefinition] = []
    hypothesis_policy = _TASK_POLICIES[PROMPT_TASK_HYPOTHESIS_GENERATION]
    for payload in DEFAULT_PROMPTS.values():
        vars_json = dict(payload.get("vars_json") or {})
        definitions.append(
            BuiltinPromptDefinition(
                capability=hypothesis_policy.capability,
                task=hypothesis_policy.task,
                name=str(payload["name"]),
                version=int(payload["version"]),
                template=str(payload["template"]),
                vars_json=vars_json,
                schema_contract=hypothesis_policy.schema_contract,
                style_profile=prompt_style_profile(vars_json),
                editable=hypothesis_policy.editable,
                source="fallback",
            )
        )

    notification_policy = _TASK_POLICIES[PROMPT_TASK_NOTIFICATION_HUMANIZE]
    notification_prompts = {"default": load_notification_prompt("")}
    for event_type in sorted(SUPPORTED_NOTIFICATION_SOURCE_EVENTS):
        prompt = load_notification_prompt(event_type)
        notification_prompts[prompt.name] = prompt
    definitions.extend(
        [
            BuiltinPromptDefinition(
                capability=notification_policy.capability,
                task=notification_policy.task,
                name=prompt.name,
                version=prompt.version,
                template=prompt.template,
                vars_json=dict(prompt.vars_json),
                schema_contract=notification_policy.schema_contract,
                style_profile=prompt_style_profile(prompt.vars_json),
                editable=notification_policy.editable,
                source="code",
            )
            for prompt in notification_prompts.values()
        ]
    )

    brief_policy = _TASK_POLICIES[PROMPT_TASK_BRIEF_GENERATE]
    definitions.extend(
        [
            BuiltinPromptDefinition(
                capability=brief_policy.capability,
                task=brief_policy.task,
                name=prompt.name,
                version=prompt.version,
                template=prompt.template,
                vars_json=dict(prompt.vars_json),
                schema_contract=brief_policy.schema_contract,
                style_profile=prompt_style_profile(prompt.vars_json),
                editable=brief_policy.editable,
                source="code",
            )
            for brief_kind in BriefKind
            for prompt in [load_brief_prompt(brief_kind)]
        ]
    )

    explain_policy = _TASK_POLICIES[PROMPT_TASK_EXPLAIN_GENERATE]
    definitions.extend(
        [
            BuiltinPromptDefinition(
                capability=explain_policy.capability,
                task=explain_policy.task,
                name=prompt.name,
                version=prompt.version,
                template=prompt.template,
                vars_json=dict(prompt.vars_json),
                schema_contract=explain_policy.schema_contract,
                style_profile=prompt_style_profile(prompt.vars_json),
                editable=explain_policy.editable,
                source="code",
            )
            for explain_kind in ExplainKind
            for prompt in [load_explanation_prompt(explain_kind)]
        ]
    )

    return tuple(sorted(definitions, key=lambda item: (item.capability.value, item.name, item.version)))


__all__ = [
    "BuiltinPromptDefinition",
    "PromptTaskPolicy",
    "get_prompt_task_policy",
    "list_builtin_prompt_definitions",
    "prompt_style_profile",
]
