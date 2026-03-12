from __future__ import annotations

import json
from typing import Any

import httpx

from src.apps.hypothesis_engine.providers.base import LLMProvider


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_chunks = [str(item.get("text", "")) for item in content if isinstance(item, dict)]
            return "".join(text_chunks)
    output_text = payload.get("output_text")
    return str(output_text) if output_text is not None else "{}"


class OpenAILikeProvider(LLMProvider):
    provider_name = "openai_like"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        timeout: float = 15.0,
    ) -> None:
        super().__init__(model=model)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def json_chat(self, prompt: str, vars: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\nContext:\n{json.dumps(vars, ensure_ascii=True, sort_keys=True, default=str)}"
                        f"\n\nSchema:\n{json.dumps(schema, ensure_ascii=True, sort_keys=True)}"
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}/chat/completions", json=request_payload, headers=headers)
            response.raise_for_status()
        content = _extract_content(response.json())
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
