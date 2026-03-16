import json
import os
from abc import ABC, abstractmethod
from typing import Any

from src.core.ai.contracts import AIContextFormat, AIProviderConfig


class AIProvider(ABC):
    def __init__(self, config: AIProviderConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    async def json_chat(self, prompt: str, vars: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        return await self.generate_structured(
            prompt=prompt,
            serialized_context=json.dumps(vars, ensure_ascii=True, sort_keys=True, default=str),
            context_format=AIContextFormat.JSON,
            schema_contract=schema,
            requested_language=None,
            effective_language="en",
        )

    @abstractmethod
    async def generate_structured(
        self,
        *,
        prompt: str,
        serialized_context: str,
        context_format: AIContextFormat,
        schema_contract: dict[str, Any] | str,
        requested_language: str | None,
        effective_language: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def resolve_auth_token(self) -> str:
        raw = self.config.auth_token or ""
        if raw.startswith("env:"):
            return os.environ.get(raw.removeprefix("env:"), "")
        return raw


__all__ = ["AIProvider"]
