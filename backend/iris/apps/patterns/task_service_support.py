from collections.abc import Mapping
from typing import cast

from iris.apps.patterns.task_service_base import PatternTaskBase
from iris.apps.patterns.task_service_context import PatternContextMixin
from iris.apps.patterns.task_service_decisions import PatternDecisionSignalsMixin
from iris.apps.patterns.task_service_history import PatternHistoryStatisticsMixin
from iris.apps.patterns.task_service_market import PatternMarketDiscoveryMixin


def payload_mapping(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        return {}
    return {str(key): value for key, value in payload.items()}


def payload_int(value: object | None, *, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float | str):
        try:
            return int(value)
        except ValueError:
            return default
    try:
        return int(cast(object, value))
    except (TypeError, ValueError):
        return default


def payload_float(value: object | None, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except ValueError:
            return default
    try:
        return float(cast(object, value))
    except (TypeError, ValueError):
        return default


def payload_string(value: object | None, *, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def payload_optional_string(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


class PatternTaskServiceSupport(
    PatternHistoryStatisticsMixin,
    PatternContextMixin,
    PatternDecisionSignalsMixin,
    PatternMarketDiscoveryMixin,
    PatternTaskBase,
):
    pass


__all__ = [
    "PatternTaskServiceSupport",
    "payload_float",
    "payload_int",
    "payload_mapping",
    "payload_optional_string",
    "payload_string",
]
