from enum import StrEnum


class LaunchMode(StrEnum):
    FULL = "full"
    LOCAL = "local"
    HA_ADDON = "ha_addon"


class DeploymentProfile(StrEnum):
    PLATFORM_FULL = "platform_full"
    PLATFORM_LOCAL = "platform_local"
    HA_EMBEDDED = "ha_embedded"


def resolve_launch_mode(value: str | LaunchMode) -> LaunchMode:
    if isinstance(value, LaunchMode):
        return value
    return LaunchMode(value.strip().lower())


def resolve_deployment_profile(
    value: str | DeploymentProfile | None,
    *,
    mode: LaunchMode,
) -> DeploymentProfile:
    if value is None or value == "":
        if mode is LaunchMode.HA_ADDON:
            return DeploymentProfile.HA_EMBEDDED
        if mode is LaunchMode.LOCAL:
            return DeploymentProfile.PLATFORM_LOCAL
        return DeploymentProfile.PLATFORM_FULL
    if isinstance(value, DeploymentProfile):
        return value
    return DeploymentProfile(value.strip().lower())
