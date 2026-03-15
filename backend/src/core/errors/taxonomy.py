from __future__ import annotations

from enum import StrEnum


class ErrorDomain(StrEnum):
    CORE = "core"
    API = "api"
    HA = "ha"


class ErrorCategory(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CONFLICT = "conflict"
    INTERNAL = "internal"
    LOCKED = "locked"
    NOT_FOUND = "not_found"
    POLICY = "policy"
    UNAVAILABLE = "unavailable"
    VALIDATION = "validation"


class ErrorSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
