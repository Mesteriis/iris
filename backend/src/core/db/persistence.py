from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

PERSISTENCE_LOGGER = logging.getLogger("iris.persistence")
_REDACTED = "<redacted>"
_ELLIPSIS = "..."
_SENSITIVE_KEYS = (
    "api_key",
    "authorization",
    "credential",
    "password",
    "secret",
    "session",
    "session_string",
    "token",
)


def freeze_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze_json_value(item) for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(freeze_json_value(item) for item in value)
    return value


def thaw_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [thaw_json_value(item) for item in value]
    return value


def sanitize_log_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key)
            if any(marker in normalized_key.lower() for marker in _SENSITIVE_KEYS):
                sanitized[normalized_key] = _REDACTED
                continue
            sanitized[normalized_key] = sanitize_log_value(item)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        items = [sanitize_log_value(item) for item in value[:5]]
        if len(value) > 5:
            items.append(_ELLIPSIS)
        return items
    if isinstance(value, str) and len(value) > 200:
        return f"{value[:197]}..."
    return value


class PersistenceComponent:
    def __init__(self, session: AsyncSession, *, component_type: str, domain: str, component_name: str) -> None:
        self._session = session
        self._component_type = component_type
        self._domain = domain
        self._component_name = component_name

    @property
    def session(self) -> AsyncSession:
        return self._session

    def _log_debug(self, event: str, /, **fields: Any) -> None:
        self._log(logging.DEBUG, event, **fields)

    def _log_info(self, event: str, /, **fields: Any) -> None:
        self._log(logging.INFO, event, **fields)

    def _log_warning(self, event: str, /, **fields: Any) -> None:
        self._log(logging.WARNING, event, **fields)

    def _log_exception(self, event: str, /, **fields: Any) -> None:
        self._log(logging.ERROR, event, exc_info=True, **fields)

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        payload = {
            "event": event,
            "component_type": self._component_type,
            "domain": self._domain,
            "component": self._component_name,
            **{key: sanitize_log_value(value) for key, value in fields.items()},
        }
        PERSISTENCE_LOGGER.log(level, event, extra={"persistence": payload})


class AsyncRepository(PersistenceComponent):
    def __init__(self, session: AsyncSession, *, domain: str, repository_name: str) -> None:
        super().__init__(
            session,
            component_type="repository",
            domain=domain,
            component_name=repository_name,
        )


class AsyncQueryService(PersistenceComponent):
    def __init__(self, session: AsyncSession, *, domain: str, service_name: str) -> None:
        super().__init__(
            session,
            component_type="query_service",
            domain=domain,
            component_name=service_name,
        )


__all__ = [
    "AsyncQueryService",
    "AsyncRepository",
    "PERSISTENCE_LOGGER",
    "PersistenceComponent",
    "freeze_json_value",
    "sanitize_log_value",
    "thaw_json_value",
]
