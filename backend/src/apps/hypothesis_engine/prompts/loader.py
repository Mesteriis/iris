from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.hypothesis_engine.memory.cache import cache_active_prompt_async, invalidate_prompt_cache_async, read_cached_active_prompt_async
from src.apps.hypothesis_engine.models import AIPrompt
from src.apps.hypothesis_engine.prompts.defaults import get_fallback_prompt


@dataclass(slots=True, frozen=True)
class LoadedPrompt:
    name: str
    task: str
    version: int
    template: str
    vars_json: dict[str, Any]
    source: str


def _normalize_prompt_payload(payload: dict[str, Any], *, source: str) -> LoadedPrompt:
    return LoadedPrompt(
        name=str(payload["name"]),
        task=str(payload["task"]),
        version=int(payload["version"]),
        template=str(payload["template"]),
        vars_json=dict(payload.get("vars_json") or {}),
        source=source,
    )


class PromptLoader:
    def __init__(self, db: AsyncSession | None = None) -> None:
        self._db = db

    async def get(self, name: str) -> str:
        return (await self.load(name)).template

    async def load(self, name: str) -> LoadedPrompt:
        cached = await read_cached_active_prompt_async(name)
        if cached is not None:
            return _normalize_prompt_payload(cached, source="redis")

        if self._db is not None:
            prompt = await self._db.scalar(
                select(AIPrompt)
                .where(AIPrompt.name == name, AIPrompt.is_active.is_(True))
                .order_by(AIPrompt.version.desc(), AIPrompt.id.desc())
                .limit(1)
            )
            if prompt is not None:
                payload = {
                    "name": prompt.name,
                    "task": prompt.task,
                    "version": int(prompt.version),
                    "template": prompt.template,
                    "vars_json": dict(prompt.vars_json or {}),
                }
                await cache_active_prompt_async(name, payload)
                return _normalize_prompt_payload(payload, source="db")

        fallback = get_fallback_prompt(name)
        await cache_active_prompt_async(name, fallback)
        return _normalize_prompt_payload(fallback, source="fallback")

    async def invalidate(self, name: str) -> None:
        await invalidate_prompt_cache_async(name)
