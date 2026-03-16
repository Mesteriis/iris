import json
from typing import Any

import httpx

from src.core.ai.contracts import AIContextFormat
from src.core.ai.providers.base import AIProvider


class LocalHTTPProvider(AIProvider):
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
        endpoint = self.config.endpoint if self.config.endpoint.startswith("/") else f"/{self.config.endpoint}"
        schema_payload = (
            json.dumps(schema_contract, ensure_ascii=True, sort_keys=True)
            if isinstance(schema_contract, dict)
            else str(schema_contract)
        )
        request_payload = {
            "model": self.model,
            "prompt": (
                f"{prompt}\n\n"
                f"Language contract:\n"
                f"- requested_language: {requested_language or 'null'}\n"
                f"- effective_language: {effective_language}\n\n"
                f"Context format: {context_format.value}\n"
                f"Context:\n{serialized_context}\n\n"
                f"Schema:\n{schema_payload}"
            ),
            "format": "json",
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        token = self.resolve_auth_token()
        if token:
            header_value = f"{self.config.auth_scheme} {token}".strip() if self.config.auth_scheme else token
            headers[self.config.auth_header] = header_value
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(f"{self.config.base_url.rstrip('/')}{endpoint}", json=request_payload, headers=headers)
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


__all__ = ["LocalHTTPProvider"]
