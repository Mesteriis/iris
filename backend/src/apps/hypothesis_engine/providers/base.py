from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    provider_name: str

    def __init__(self, *, model: str) -> None:
        self.model = model

    @abstractmethod
    async def json_chat(self, prompt: str, vars: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
