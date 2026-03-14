from __future__ import annotations

import json
from typing import Any

import httpx

from src.core.ai.contracts import AIContextFormat
from src.core.ai.providers.base import AIProvider


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


class OpenAILikeProvider(AIProvider):
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
        schema_payload = (
            json.dumps(schema_contract, ensure_ascii=True, sort_keys=True)
            if isinstance(schema_contract, dict)
            else str(schema_contract)
        )
        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\n"
                        f"Language contract:\n"
                        f"- requested_language: {requested_language or 'null'}\n"
                        f"- effective_language: {effective_language}\n\n"
                        f"Context format: {context_format.value}\n"
                        f"Context:\n{serialized_context}\n\n"
                        f"Schema:\n{schema_payload}"
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        endpoint = self.config.endpoint if self.config.endpoint.startswith("/") else f"/{self.config.endpoint}"
        headers = {"Content-Type": "application/json"}
        token = self.resolve_auth_token()
        if token:
            header_value = f"{self.config.auth_scheme} {token}".strip() if self.config.auth_scheme else token
            headers[self.config.auth_header] = header_value
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.config.base_url.rstrip('/')}{endpoint}",
                json=request_payload,
                headers=headers,
            )
            response.raise_for_status()
        content = _extract_content(response.json())
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}


__all__ = ["OpenAILikeProvider"]
