from __future__ import annotations

import json
from typing import Any

import httpx

from src.apps.hypothesis_engine.providers.base import LLMProvider


class LocalHTTPProvider(LLMProvider):
    provider_name = "local_http"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        endpoint: str = "/api/generate",
        timeout: float = 15.0,
    ) -> None:
        super().__init__(model=model)
        self._base_url = base_url.rstrip("/")
        self._endpoint = endpoint
        self._timeout = timeout

    async def json_chat(self, prompt: str, vars: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        endpoint = self._endpoint if self._endpoint.startswith("/") else f"/{self._endpoint}"
        request_payload = {
            "model": self.model,
            "prompt": (
                f"{prompt}\n\nContext:\n{json.dumps(vars, ensure_ascii=True, sort_keys=True, default=str)}"
                f"\n\nSchema:\n{json.dumps(schema, ensure_ascii=True, sort_keys=True)}"
            ),
            "format": "json",
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}{endpoint}", json=request_payload)
            response.raise_for_status()
        payload = response.json()
        raw = payload.get("response")
        if raw is None:
            message = payload.get("message", {})
            raw = message.get("content") if isinstance(message, dict) else payload
        if isinstance(raw, dict):
            return raw
        parsed = json.loads(str(raw or "{}"))
        return parsed if isinstance(parsed, dict) else {}
