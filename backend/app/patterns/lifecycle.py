from __future__ import annotations

from enum import StrEnum


class PatternLifecycleState(StrEnum):
    ACTIVE = "ACTIVE"
    EXPERIMENTAL = "EXPERIMENTAL"
    COOLDOWN = "COOLDOWN"
    DISABLED = "DISABLED"


def lifecycle_allows_detection(state: str, enabled: bool) -> bool:
    return enabled and state not in {PatternLifecycleState.DISABLED, PatternLifecycleState.COOLDOWN}
