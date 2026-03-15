from __future__ import annotations

from src.apps.ai_prompt_registry import ensure_ai_prompt_policy_loaded
from src.apps.hypothesis_engine.constants import FORBIDDEN_PROMPT_INFRA_KEYS
from src.apps.hypothesis_engine.contracts import PromptCacheInvalidation, PromptMutationResult, PromptRecord
from src.apps.hypothesis_engine.exceptions import (
    InvalidPromptPayloadError,
    PromptNotFoundError,
    PromptVeilLockedError,
)
from src.apps.hypothesis_engine.models import AIPrompt
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.hypothesis_engine.repositories import HypothesisRepository
from src.apps.hypothesis_engine.schemas import AIPromptCreate, AIPromptUpdate
from src.core.ai.prompt_policy import get_prompt_task_policy, prompt_style_profile
from src.core.db.uow import BaseAsyncUnitOfWork


class PromptService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        ensure_ai_prompt_policy_loaded()
        self._uow = uow
        self._repo = HypothesisRepository(uow.session)
        self._queries = HypothesisQueryService(uow.session)

    async def list_prompts(self, *, name: str | None = None) -> list[PromptRecord]:
        return [self._prompt_record(prompt) for prompt in await self._queries.list_prompts(name=name)]

    async def create_prompt(self, payload: AIPromptCreate) -> PromptMutationResult:
        name = payload.name.strip()
        task = payload.task.strip()
        version = int(payload.version)
        vars_json = self._normalize_prompt_vars(task=task, vars_json=payload.vars_json)
        existing = await self._repo.get_prompt_by_name_version(name=name, version=version)
        if existing is not None:
            raise InvalidPromptPayloadError(
                f"Prompt '{name}' version '{version}' already exists."
            )
        family = await self._repo.list_prompts_for_update(name=name)
        if not family:
            raise InvalidPromptPayloadError(
                f"Prompt family '{name}' is not provisioned. Baseline prompts must be seeded by migration."
            )
        canonical_task = str(family[0].task)
        if task != canonical_task:
            raise InvalidPromptPayloadError(
                f"Prompt family '{name}' is bound to task '{canonical_task}', not '{task}'."
            )
        self._require_veil_lifted(name=name, prompt=family[0])
        prompt = await self._repo.add_prompt(
            AIPrompt(
                name=name,
                task=canonical_task,
                version=version,
                veil_lifted=True,
                is_active=False,
                template=payload.template,
                vars_json=vars_json,
            )
        )
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        record = self._prompt_record(item if item is not None else prompt)
        return PromptMutationResult(
            prompt=record,
            cache_invalidations=(PromptCacheInvalidation(name=record.name),),
        )

    async def update_prompt(self, prompt_id: int, payload: AIPromptUpdate) -> PromptMutationResult:
        prompt = await self._repo.get_prompt_for_update(prompt_id)
        if prompt is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' was not found.")
        self._require_veil_lifted(name=prompt.name, prompt=prompt)
        next_task = prompt.task if payload.task is None else payload.task.strip()
        if next_task != prompt.task:
            raise InvalidPromptPayloadError(f"Prompt family '{prompt.name}' is bound to task '{prompt.task}'.")
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
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        record = self._prompt_record(item if item is not None else prompt)
        return PromptMutationResult(
            prompt=record,
            cache_invalidations=(PromptCacheInvalidation(name=record.name),),
        )

    async def activate_prompt(self, prompt_id: int) -> PromptMutationResult:
        prompt = await self._repo.get_prompt_for_update(prompt_id)
        if prompt is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' was not found.")
        self._require_veil_lifted(name=prompt.name, prompt=prompt)
        prompt.is_active = True
        await self._deactivate_other_versions(prompt)
        await self._uow.flush()
        await self._repo.refresh(prompt)
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        record = self._prompt_record(item if item is not None else prompt)
        return PromptMutationResult(
            prompt=record,
            cache_invalidations=(PromptCacheInvalidation(name=record.name),),
        )

    async def lift_prompt_veil(self, prompt_id: int) -> PromptMutationResult:
        prompt = await self._repo.get_prompt_for_update(prompt_id)
        if prompt is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' was not found.")
        for item in await self._repo.list_prompts_for_update(name=prompt.name):
            item.veil_lifted = True
        await self._uow.flush()
        await self._repo.refresh(prompt)
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        record = self._prompt_record(item if item is not None else prompt)
        return PromptMutationResult(prompt=record)

    async def lower_prompt_veil(self, prompt_id: int) -> PromptMutationResult:
        prompt = await self._repo.get_prompt_for_update(prompt_id)
        if prompt is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' was not found.")
        for item in await self._repo.list_prompts_for_update(name=prompt.name):
            item.veil_lifted = False
        await self._uow.flush()
        await self._repo.refresh(prompt)
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        record = self._prompt_record(item if item is not None else prompt)
        return PromptMutationResult(prompt=record)

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
        normalized = {str(key).strip(): value for key, value in dict(vars_json).items()}
        self._validate_prompt_vars(normalized)
        if prompt_style_profile(normalized) is None:
            raise InvalidPromptPayloadError("Prompt vars must include a non-empty 'style_profile'.")
        return normalized

    def _require_veil_lifted(self, *, name: str, prompt: AIPrompt) -> None:
        if bool(prompt.veil_lifted):
            return
        raise PromptVeilLockedError(
            f"Prompt family '{name}' is veiled. Lift the veil before creating, updating or activating prompt versions."
        )

    def _prompt_record(self, source) -> PromptRecord:
        return PromptRecord(
            id=int(source.id),
            name=str(source.name),
            task=str(source.task),
            version=int(source.version),
            veil_lifted=bool(source.veil_lifted),
            is_active=bool(source.is_active),
            template=str(source.template),
            vars_json=dict(source.vars_json or {}),
            updated_at=getattr(source, "updated_at", None),
        )
