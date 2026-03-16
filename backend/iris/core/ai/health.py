from iris.core.ai.capabilities import ai_capability_is_available
from iris.core.ai.contracts import AICapability, AIHealthState
from iris.core.settings import Settings, get_settings


def capability_health_state(capability: AICapability, settings: Settings | None = None) -> AIHealthState:
    effective_settings = settings or get_settings()
    if ai_capability_is_available(capability, effective_settings):
        return AIHealthState.HEALTHY
    return AIHealthState.OFFLINE


__all__ = ["capability_health_state"]
