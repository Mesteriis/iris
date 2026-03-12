from __future__ import annotations

from src.apps.hypothesis_engine.exceptions import InvalidPromptPayloadError, PromptNotFoundError
from src.apps.hypothesis_engine.models import AIPrompt
from src.apps.hypothesis_engine.prompts import PromptLoader
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.hypothesis_engine.repositories import HypothesisRepository
from src.apps.hypothesis_engine.schemas import AIPromptCreate, AIPromptRead, AIPromptUpdate
from src.core.db.uow import BaseAsyncUnitOfWork


class PromptService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._repo = HypothesisRepository(uow.session)
        self._queries = HypothesisQueryService(uow.session)
        self._loader = PromptLoader(uow.session)

    async def list_prompts(self, *, name: str | None = None) -> list[AIPromptRead]:
        return [AIPromptRead.model_validate(prompt) for prompt in await self._queries.list_prompts(name=name)]

    async def create_prompt(self, payload: AIPromptCreate) -> AIPromptRead:
        existing = await self._repo.get_prompt_by_name_version(name=payload.name.strip(), version=int(payload.version))
        if existing is not None:
            raise InvalidPromptPayloadError(
                f"Prompt '{payload.name.strip()}' version '{int(payload.version)}' already exists."
            )
        prompt = await self._repo.add_prompt(
            AIPrompt(
                name=payload.name.strip(),
                task=payload.task.strip(),
                version=int(payload.version),
                is_active=False,
                template=payload.template,
                vars_json=dict(payload.vars_json),
            )
        )
        await self._uow.commit()
        await self._loader.invalidate(prompt.name)
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        return AIPromptRead.model_validate(item if item is not None else prompt)

    async def update_prompt(self, prompt_id: int, payload: AIPromptUpdate) -> AIPromptRead:
        prompt = await self._repo.get_prompt_for_update(prompt_id)
        if prompt is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' was not found.")
        if payload.task is not None:
            prompt.task = payload.task.strip()
        if payload.template is not None:
            prompt.template = payload.template
        if payload.vars_json is not None:
            prompt.vars_json = dict(payload.vars_json)
        if payload.is_active is not None:
            prompt.is_active = bool(payload.is_active)
            if prompt.is_active:
                await self._deactivate_other_versions(prompt)
        await self._uow.commit()
        await self._repo.refresh(prompt)
        await self._loader.invalidate(prompt.name)
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        return AIPromptRead.model_validate(item if item is not None else prompt)

    async def activate_prompt(self, prompt_id: int) -> AIPromptRead:
        prompt = await self._repo.get_prompt_for_update(prompt_id)
        if prompt is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' was not found.")
        prompt.is_active = True
        await self._deactivate_other_versions(prompt)
        await self._uow.commit()
        await self._repo.refresh(prompt)
        await self._loader.invalidate(prompt.name)
        item = await self._queries.get_prompt_read_by_id(int(prompt.id))
        return AIPromptRead.model_validate(item if item is not None else prompt)

    async def _deactivate_other_versions(self, prompt: AIPrompt) -> None:
        for item in await self._repo.list_prompts_for_update(name=prompt.name):
            item.is_active = int(item.id) == int(prompt.id)
