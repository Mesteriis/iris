from collections.abc import Mapping, Sequence
from typing import Any

from iris.core.errors import PLATFORM_ERROR_REGISTRY, PlatformError


class HACommandDispatchError(PlatformError):
    """Typed HA bridge command failure with registry-backed metadata."""


class HACommandNotAvailableError(HACommandDispatchError):
    def __init__(self, *, command: str, mode: str, locale: str | None = None) -> None:
        super().__init__(
            PLATFORM_ERROR_REGISTRY.get("command_not_available"),
            params={"command": command},
            details={"command": command, "mode": mode},
            locale=locale,
        )


class HAInvalidPayloadError(HACommandDispatchError):
    def __init__(
        self,
        *,
        command: str,
        payload: Mapping[str, Any],
        expected: str,
        allowed_values: Sequence[str] | None = None,
        locale: str | None = None,
    ) -> None:
        details: dict[str, object] = {
            "command": command,
            "payload": dict(payload),
            "expected": expected,
        }
        if allowed_values is not None:
            details["allowed_values"] = list(allowed_values)
        super().__init__(
            PLATFORM_ERROR_REGISTRY.get("invalid_payload"),
            params={"command": command},
            details=details,
            locale=locale,
        )
