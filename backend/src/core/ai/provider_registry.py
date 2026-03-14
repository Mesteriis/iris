from __future__ import annotations

from collections.abc import Iterable

from src.core.ai.contracts import AICapability, AIProviderConfig, AIProviderKind
from src.core.ai.providers.base import AIProvider
from src.core.ai.providers.local_http import LocalHTTPProvider
from src.core.ai.providers.openai_like import OpenAILikeProvider
from src.core.ai.settings import build_provider_configs
from src.core.settings import Settings, get_settings


class AIProviderRegistry:
    def __init__(self, providers: Iterable[AIProviderConfig]) -> None:
        enabled = [provider for provider in providers if provider.enabled]
        self._providers = tuple(sorted(enabled, key=lambda item: item.priority, reverse=True))
        self._by_name = {provider.name: provider for provider in self._providers}

    def providers_for(self, capability: AICapability) -> tuple[AIProviderConfig, ...]:
        return tuple(provider for provider in self._providers if capability in provider.capabilities)

    def has_real_provider_for(self, capability: AICapability) -> bool:
        return bool(self.providers_for(capability))

    def resolve(self, *, capability: AICapability, requested_provider: str | None = None) -> AIProviderConfig:
        if requested_provider is not None:
            provider = self._by_name.get(str(requested_provider).strip())
            if provider is None or capability not in provider.capabilities:
                raise LookupError(f"Provider '{requested_provider}' is not enabled for capability '{capability.value}'.")
            return provider
        providers = self.providers_for(capability)
        if not providers:
            raise LookupError(f"No enabled provider is configured for capability '{capability.value}'.")
        return providers[0]

    def instantiate(self, provider: AIProviderConfig) -> AIProvider:
        if provider.kind is AIProviderKind.OPENAI_LIKE:
            return OpenAILikeProvider(provider)
        if provider.kind is AIProviderKind.LOCAL_HTTP:
            return LocalHTTPProvider(provider)
        raise LookupError(f"Unsupported AI provider kind '{provider.kind.value}'.")


def build_provider_registry(settings: Settings | None = None) -> AIProviderRegistry:
    effective_settings = settings or get_settings()
    return AIProviderRegistry(build_provider_configs(effective_settings))


__all__ = ["AIProviderRegistry", "build_provider_registry"]
