from typing import Any

from src.core.ai.contracts import AICapability, AIProviderConfig, AIProviderKind
from src.core.settings import Settings

_DEFAULT_PROVIDER_CAPABILITIES: tuple[AICapability, ...] = (
    AICapability.HYPOTHESIS_GENERATE,
    AICapability.NOTIFICATION_HUMANIZE,
    AICapability.BRIEF_GENERATE,
    AICapability.EXPLAIN_GENERATE,
)


def _normalize_capabilities(raw: object) -> tuple[AICapability, ...]:
    values = raw if isinstance(raw, list) else [cap.strip() for cap in str(raw or "").split(",") if cap.strip()]
    capabilities = [AICapability(str(item).strip().lower()) for item in values]
    return tuple(capabilities or _DEFAULT_PROVIDER_CAPABILITIES)


def _build_provider_config(item: dict[str, Any]) -> AIProviderConfig:
    return AIProviderConfig(
        name=str(item.get("name") or "").strip(),
        kind=AIProviderKind(str(item.get("kind") or "").strip().lower()),
        enabled=bool(item.get("enabled", True)),
        base_url=str(item.get("base_url") or "").strip(),
        endpoint=str(item.get("endpoint") or "").strip() or "/",
        auth_token=str(item.get("auth_token") or "").strip() or None,
        auth_header=str(item.get("auth_header") or "Authorization").strip(),
        auth_scheme=str(item.get("auth_scheme") or "").strip() or None,
        model=str(item.get("model") or "").strip(),
        timeout_seconds=float(item.get("timeout_seconds") or 15.0),
        priority=int(item.get("priority") or 0),
        capabilities=_normalize_capabilities(item.get("capabilities")),
        metadata=dict(item.get("metadata") or {}),
        max_context_tokens=int(item["max_context_tokens"]) if item.get("max_context_tokens") is not None else None,
        max_output_tokens=int(item["max_output_tokens"]) if item.get("max_output_tokens") is not None else None,
    )


def build_provider_configs(settings: Settings) -> tuple[AIProviderConfig, ...]:
    explicit = {
        str(item.get("name") or "").strip(): _build_provider_config(dict(item))
        for item in settings.ai_providers
        if str(item.get("name") or "").strip()
    }
    if settings.ai_openai_enabled and "openai_primary" not in explicit:
        explicit["openai_primary"] = AIProviderConfig(
            name="openai_primary",
            kind=AIProviderKind.OPENAI_LIKE,
            enabled=True,
            base_url=settings.ai_openai_base_url,
            endpoint=settings.ai_openai_endpoint,
            auth_token=settings.ai_openai_api_key or None,
            auth_header="Authorization",
            auth_scheme="Bearer",
            model=settings.ai_openai_model,
            timeout_seconds=15.0,
            priority=100,
            capabilities=_DEFAULT_PROVIDER_CAPABILITIES,
        )
    if settings.ai_local_http_enabled and "local_http_primary" not in explicit:
        explicit["local_http_primary"] = AIProviderConfig(
            name="local_http_primary",
            kind=AIProviderKind.LOCAL_HTTP,
            enabled=True,
            base_url=settings.ai_local_http_base_url,
            endpoint=settings.ai_local_http_endpoint,
            auth_token=None,
            auth_header="Authorization",
            auth_scheme=None,
            model=settings.ai_local_http_model,
            timeout_seconds=15.0,
            priority=50,
            capabilities=_DEFAULT_PROVIDER_CAPABILITIES,
        )
    return tuple(sorted(explicit.values(), key=lambda item: item.priority, reverse=True))


def build_capability_overrides(settings: Settings) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}
    for capability_name, raw in settings.ai_capabilities.items():
        if not isinstance(raw, dict):
            continue
        overrides[str(capability_name).strip().lower()] = dict(raw)
    return overrides


__all__ = ["build_capability_overrides", "build_provider_configs"]
