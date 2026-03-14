from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class BriefKind(StrEnum):
    MARKET = "market"
    SYMBOL = "symbol"
    PORTFOLIO = "portfolio"


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


__all__ = ["BriefGenerationOutput", "BriefKind", "build_scope_key"]
