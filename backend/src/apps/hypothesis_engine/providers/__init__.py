from __future__ import annotations

from typing import Any

from src.apps.hypothesis_engine.constants import PROVIDER_HEURISTIC, PROVIDER_LOCAL_HTTP, PROVIDER_OPENAI_LIKE
from src.apps.hypothesis_engine.exceptions import UnsupportedLLMProviderError
from src.apps.hypothesis_engine.providers.base import LLMProvider
from src.apps.hypothesis_engine.providers.heuristic import HeuristicProvider
from src.apps.hypothesis_engine.providers.local_http import LocalHTTPProvider
from src.apps.hypothesis_engine.providers.openai_like import OpenAILikeProvider
from src.core.settings import get_settings


def create_provider(name: str, *, model: str | None = None, config: dict[str, Any] | None = None) -> LLMProvider:
    settings = get_settings()
    effective_name = str(name or PROVIDER_HEURISTIC).strip().lower()
    options = dict(config or {})
    if effective_name == PROVIDER_HEURISTIC:
        return HeuristicProvider(model=model or str(options.get("model") or "rule-based"))
    if effective_name == PROVIDER_OPENAI_LIKE:
        return OpenAILikeProvider(
            model=model or str(options.get("model") or settings.ai_openai_model),
            base_url=str(options.get("base_url") or settings.ai_openai_base_url),
            api_key=str(options.get("api_key") or settings.ai_openai_api_key),
            timeout=float(options.get("timeout") or 15.0),
        )
    if effective_name == PROVIDER_LOCAL_HTTP:
        return LocalHTTPProvider(
            model=model or str(options.get("model") or settings.ai_local_http_model),
            base_url=str(options.get("base_url") or settings.ai_local_http_base_url),
            endpoint=str(options.get("endpoint") or "/api/generate"),
            timeout=float(options.get("timeout") or 15.0),
        )
    raise UnsupportedLLMProviderError(f"Unsupported hypothesis provider '{name}'.")


__all__ = [
    "LLMProvider",
    "HeuristicProvider",
    "LocalHTTPProvider",
    "OpenAILikeProvider",
    "create_provider",
]
