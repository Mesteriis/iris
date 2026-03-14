from __future__ import annotations

from typing import Literal

from src.apps.briefs.contracts import BriefKind
from src.apps.briefs.schemas import BriefRead
from src.core.http.contracts import AcceptedResponse


class BriefJobAcceptedRead(AcceptedResponse):
    operation_type: Literal["brief.generate"] = "brief.generate"
    brief_kind: BriefKind
    scope_key: str
    language: str
    symbol: str | None = None


__all__ = ["BriefJobAcceptedRead", "BriefRead"]
