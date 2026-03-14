from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class NewsSourcePollResult:
    status: str
    source_id: int
    plugin_name: str | None = None
    fetched: int = 0
    created: int = 0
    cursor: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None


@dataclass(slots=True, frozen=True)
class NewsEnabledPollResult:
    status: str
    sources: int
    created: int
    items: tuple[NewsSourcePollResult, ...] = ()


__all__ = ["NewsEnabledPollResult", "NewsSourcePollResult"]
