from __future__ import annotations

from typing import Literal

from src.apps.explanations.contracts import ExplainKind
from src.apps.explanations.schemas import ExplanationRead
from src.core.http.contracts import AcceptedResponse


class ExplanationJobAcceptedRead(AcceptedResponse):
    operation_type: Literal["explain.generate"] = "explain.generate"
    explain_kind: ExplainKind
    subject_id: int
    language: str
    symbol: str | None = None
    timeframe: int | None = None


__all__ = ["ExplanationJobAcceptedRead", "ExplanationRead"]
