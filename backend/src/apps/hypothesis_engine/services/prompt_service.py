from __future__ import annotations

from src.apps.ai_prompt_registry import ensure_ai_prompt_policy_loaded
from src.apps.hypothesis_engine.constants import FORBIDDEN_PROMPT_INFRA_KEYS
from src.apps.hypothesis_engine.exceptions import InvalidPromptPayloadError, PromptNotFoundError
from src.apps.hypothesis_engine.models import AIPrompt
from src.apps.hypothesis_engine.prompts import PromptLoader
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.hypothesis_engine.repositories import HypothesisRepository
from src.apps.hypothesis_engine.schemas import AIPromptCreate, AIPromptRead, AIPromptUpdate
from src.core.ai.prompt_policy import get_prompt_task_policy, prompt_style_profile
from src.core.db.uow import BaseAsyncUnitOfWork


class PromptService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        ensure_ai_prompt_policy_loaded()
        self._uow = uow
        self._repo = HypothesisRepository(uow.session)
        self._queries = HypothesisQueryService(uow.session)
        self._loader = PromptLoader(self._queries)

    async def list_prompts(self, *, name: str | None = None) -> list[AIPromptRead]:
        return [AIPromptRead.model_validate(prompt) for prompt in await self._queries.list_prompts(name=name)]

    async def create_prompt(self, payload: AIPromptCreate) -> AIPromptRead:
        task = payload.task.strip()
        vars_json = self._normalize_prompt_vars(task=task, vars_json=payload.vars_json)
        existing = await self._repo.get_prompt_by_name_version(name=payload.name.strip(), version=int(payload.version))
        if existing is not None:
            raise InvalidPromptPayloadError(
                f"Prompt '{payload.name.strip()}' version '{int(payload.version)}' already exists."
            )
        prompt = await self._repo.add_prompt(
            AIPrompt(
                name=payload.name.strip(),
                task=task,
                version=int(payload.version),
                is_active=False,
                template=payload.template,
                vars_json=vars_json,
            )
        )
        self._uow.add_after_commit_action(lambda name=prompt.name: self._loader.invalidate(name))
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        return AIPromptRead.model_validate(item if item is not None else prompt)

    async def update_prompt(self, prompt_id: int, payload: AIPromptUpdate) -> AIPromptRead:
        prompt = await self._repo.get_prompt_for_update(prompt_id)
        if prompt is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' was not found.")
        next_task = prompt.task if payload.task is None else payload.task.strip()
        if payload.template is not None:
            prompt.template = payload.template
        if payload.task is not None:
            prompt.task = next_task
        if payload.vars_json is not None or payload.task is not None:
            next_vars = dict(prompt.vars_json or {}) if payload.vars_json is None else dict(payload.vars_json)
            prompt.vars_json = self._normalize_prompt_vars(task=next_task, vars_json=next_vars)
        if payload.is_active is not None:
            prompt.is_active = bool(payload.is_active)
            if prompt.is_active:
                await self._deactivate_other_versions(prompt)
        await self._uow.flush()
        await self._repo.refresh(prompt)
        self._uow.add_after_commit_action(lambda name=prompt.name: self._loader.invalidate(name))
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        return AIPromptRead.model_validate(item if item is not None else prompt)

    async def activate_prompt(self, prompt_id: int) -> AIPromptRead:
        prompt = await self._repo.get_prompt_for_update(prompt_id)
        if prompt is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' was not found.")
        prompt.is_active = True
        await self._deactivate_other_versions(prompt)
        await self._uow.flush()
        await self._repo.refresh(prompt)
        self._uow.add_after_commit_action(lambda name=prompt.name: self._loader.invalidate(name))
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        return AIPromptRead.model_validate(item if item is not None else prompt)

    async def _deactivate_other_versions(self, prompt: AIPrompt) -> None:
        for item in await self._repo.list_prompts_for_update(name=prompt.name):
            item.is_active = int(item.id) == int(prompt.id)

    def _validate_prompt_vars(self, vars_json: dict[str, object]) -> None:
        forbidden = sorted(FORBIDDEN_PROMPT_INFRA_KEYS.intersection({str(key).strip() for key in vars_json}))
        if forbidden:
            names = ", ".join(forbidden)
            raise InvalidPromptPayloadError(
                f"Prompt vars cannot control provider infrastructure routing: {names}."
            )

    def _normalize_prompt_vars(self, *, task: str, vars_json: dict[str, object]) -> dict[str, object]:
        policy = get_prompt_task_policy(task)
        if policy is None:
            raise InvalidPromptPayloadError(f"Prompt task '{task}' is not registered in the shared AI task policy.")
        if not policy.editable:
            raise InvalidPromptPayloadError(f"Prompt task '{task}' is code-managed and cannot be edited via operator API.")
        normalized = {str(key).strip(): value for key, value in dict(vars_json).items()}
        self._validate_prompt_vars(normalized)
        if prompt_style_profile(normalized) is None:
            raise InvalidPromptPayloadError("Prompt vars must include a non-empty 'style_profile'.")
        return normalized
