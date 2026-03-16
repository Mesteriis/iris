from enum import StrEnum


class PatternLifecycleState(StrEnum):
    ACTIVE = "ACTIVE"
    EXPERIMENTAL = "EXPERIMENTAL"
    COOLDOWN = "COOLDOWN"
    DISABLED = "DISABLED"


def lifecycle_allows_detection(state: str, enabled: bool) -> bool:
    return enabled and state not in {PatternLifecycleState.DISABLED, PatternLifecycleState.COOLDOWN}


def resolve_lifecycle_state(temperature: float, enabled: bool) -> PatternLifecycleState:
    if not enabled:
        return PatternLifecycleState.DISABLED
    if temperature <= -1.0:
        return PatternLifecycleState.DISABLED
    if temperature <= -0.2:
        return PatternLifecycleState.COOLDOWN
    if temperature < 0.2:
        return PatternLifecycleState.EXPERIMENTAL
    return PatternLifecycleState.ACTIVE
