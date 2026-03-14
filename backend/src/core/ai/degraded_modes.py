from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any

from src.core.ai.contracts import AICapability

DegradedHandler = Callable[[AICapability, str, dict[str, Any], str | None, str], Awaitable[dict[str, Any]] | dict[str, Any]]


@dataclass(frozen=True, slots=True)
class CallableDegradedStrategy:
    name: str
    handler: DegradedHandler

    async def execute(
        self,
        *,
        capability: AICapability,
        task: str,
        context: dict[str, Any],
        requested_language: str | None,
        effective_language: str,
    ) -> dict[str, Any]:
        result = self.handler(capability, task, context, requested_language, effective_language)
        if isawaitable(result):
            resolved = await result
        else:
            resolved = result
        return dict(resolved)


__all__ = ["CallableDegradedStrategy"]
