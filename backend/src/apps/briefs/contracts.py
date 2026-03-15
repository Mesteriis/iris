from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class BriefKind(StrEnum):
    MARKET = "market"
    SYMBOL = "symbol"
    PORTFOLIO = "portfolio"


class BriefGenerationStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"


def build_scope_key(brief_kind: BriefKind, *, symbol: str | None = None) -> str:
    if brief_kind is BriefKind.MARKET:
        return "market"
    if brief_kind is BriefKind.PORTFOLIO:
        return "portfolio"
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        raise ValueError("Symbol brief scope requires a symbol.")
    return f"symbol:{normalized_symbol}"


class BriefGenerationOutput(BaseModel):
    title: str
    summary: str
    bullets: list[str]

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True, slots=True)
class BriefGenerationResult:
    status: BriefGenerationStatus
    brief_id: int
    brief_kind: BriefKind
    scope_key: str
    language: str
    symbol: str | None = None
    reason: str | None = None
    generated_at: datetime | None = None
    source_updated_at: datetime | None = None


__all__ = [
    "BriefGenerationOutput",
    "BriefGenerationResult",
    "BriefGenerationStatus",
    "BriefKind",
    "build_scope_key",
]
