from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class EnrichedAnomalyProjection:
    payload_json: dict[str, Any]
    portfolio_relevant: bool
    market_wide: bool


__all__ = ["EnrichedAnomalyProjection"]
