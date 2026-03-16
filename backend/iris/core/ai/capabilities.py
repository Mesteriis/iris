from iris.core.ai.contracts import AICapability, AICapabilityPolicy, AIContextFormat
from iris.core.ai.provider_registry import AIProviderRegistry, build_provider_registry
from iris.core.ai.settings import build_capability_overrides
from iris.core.http.launch_modes import DeploymentProfile, LaunchMode, resolve_deployment_profile, resolve_launch_mode
from iris.core.settings import Settings, get_settings

_DEFAULT_POLICIES: dict[AICapability, AICapabilityPolicy] = {
    AICapability.HYPOTHESIS_GENERATE: AICapabilityPolicy(
        capability=AICapability.HYPOTHESIS_GENERATE,
        enabled=True,
        allow_degraded_fallback=True,
        preferred_context_format=AIContextFormat.JSON,
        allowed_context_formats=(AIContextFormat.JSON, AIContextFormat.COMPACT_JSON),
    ),
    AICapability.NOTIFICATION_HUMANIZE: AICapabilityPolicy(
        capability=AICapability.NOTIFICATION_HUMANIZE,
        enabled=True,
        allow_degraded_fallback=True,
        preferred_context_format=AIContextFormat.JSON,
        allowed_context_formats=(AIContextFormat.JSON, AIContextFormat.COMPACT_JSON),
    ),
    AICapability.BRIEF_GENERATE: AICapabilityPolicy(
        capability=AICapability.BRIEF_GENERATE,
        enabled=True,
        allow_degraded_fallback=False,
        preferred_context_format=AIContextFormat.JSON,
        allowed_context_formats=(
            AIContextFormat.JSON,
            AIContextFormat.COMPACT_JSON,
            AIContextFormat.TOON,
            AIContextFormat.CSV,
        ),
    ),
    AICapability.EXPLAIN_GENERATE: AICapabilityPolicy(
        capability=AICapability.EXPLAIN_GENERATE,
        enabled=True,
        allow_degraded_fallback=True,
        preferred_context_format=AIContextFormat.JSON,
        allowed_context_formats=(AIContextFormat.JSON, AIContextFormat.COMPACT_JSON),
    ),
}


def _effective_profile(settings: Settings) -> DeploymentProfile:
    mode = resolve_launch_mode(settings.api_launch_mode)
    return resolve_deployment_profile(settings.api_deployment_profile, mode=mode)


def current_launch_mode(settings: Settings | None = None) -> LaunchMode:
    effective_settings = settings or get_settings()
    return resolve_launch_mode(effective_settings.api_launch_mode)


def current_deployment_profile(settings: Settings | None = None) -> DeploymentProfile:
    effective_settings = settings or get_settings()
    return _effective_profile(effective_settings)


def get_capability_policy(capability: AICapability, settings: Settings | None = None) -> AICapabilityPolicy:
    effective_settings = settings or get_settings()
    base = _DEFAULT_POLICIES[capability]
    override = build_capability_overrides(effective_settings).get(capability.value, {})
    allowed = tuple(
        AIContextFormat(str(item).strip().lower()) for item in override.get("allowed_context_formats", base.allowed_context_formats)
    )
    preferred = AIContextFormat(
        str(override.get("preferred_context_format") or base.preferred_context_format.value).strip().lower()
    )
    return AICapabilityPolicy(
        capability=capability,
        enabled=bool(override.get("enabled", base.enabled)),
        allow_degraded_fallback=bool(override.get("allow_degraded_fallback", base.allow_degraded_fallback)),
        preferred_context_format=preferred,
        allowed_context_formats=allowed or base.allowed_context_formats,
    )


def ai_capability_is_available(capability: AICapability, settings: Settings | None = None) -> bool:
    effective_settings = settings or get_settings()
    policy = get_capability_policy(capability, settings=effective_settings)
    if not policy.enabled:
        return False
    registry: AIProviderRegistry = build_provider_registry(effective_settings)
    return registry.has_real_provider_for(capability)


def ai_operator_surfaces_enabled(profile: DeploymentProfile) -> bool:
    return profile is not DeploymentProfile.HA_EMBEDDED


def hypothesis_generation_runtime_enabled(settings: Settings | None = None) -> bool:
    effective_settings = settings or get_settings()
    return (
        current_deployment_profile(effective_settings) is not DeploymentProfile.HA_EMBEDDED
        and ai_capability_is_available(AICapability.HYPOTHESIS_GENERATE, effective_settings)
    )


def hypothesis_stream_surfaces_enabled(
    *,
    settings: Settings | None = None,
    profile: DeploymentProfile | None = None,
) -> bool:
    effective_settings = settings or get_settings()
    effective_profile = profile or current_deployment_profile(effective_settings)
    return effective_profile is not DeploymentProfile.HA_EMBEDDED and ai_capability_is_available(
        AICapability.HYPOTHESIS_GENERATE,
        effective_settings,
    )


def hypothesis_evaluation_surfaces_enabled(settings: Settings | None = None) -> bool:
    effective_settings = settings or get_settings()
    return current_deployment_profile(effective_settings) is not DeploymentProfile.HA_EMBEDDED


def notification_humanization_runtime_enabled(settings: Settings | None = None) -> bool:
    effective_settings = settings or get_settings()
    return ai_capability_is_available(AICapability.NOTIFICATION_HUMANIZE, effective_settings)


def brief_generation_runtime_enabled(settings: Settings | None = None) -> bool:
    effective_settings = settings or get_settings()
    return ai_capability_is_available(AICapability.BRIEF_GENERATE, effective_settings)


def explain_generation_runtime_enabled(settings: Settings | None = None) -> bool:
    effective_settings = settings or get_settings()
    return ai_capability_is_available(AICapability.EXPLAIN_GENERATE, effective_settings)


__all__ = [
    "ai_capability_is_available",
    "ai_operator_surfaces_enabled",
    "brief_generation_runtime_enabled",
    "current_deployment_profile",
    "current_launch_mode",
    "explain_generation_runtime_enabled",
    "get_capability_policy",
    "hypothesis_evaluation_surfaces_enabled",
    "hypothesis_generation_runtime_enabled",
    "hypothesis_stream_surfaces_enabled",
    "notification_humanization_runtime_enabled",
]
