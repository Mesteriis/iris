from typing import Any

from src.apps.hypothesis_engine.degraded import build_hypothesis_degraded_output
from src.apps.hypothesis_engine.providers.base import LLMProvider


class HeuristicProvider(LLMProvider):
    provider_name = "heuristic"

    async def json_chat(self, prompt: str, vars: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        del prompt, schema
        return build_hypothesis_degraded_output(vars)
