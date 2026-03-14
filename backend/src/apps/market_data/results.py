from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class MarketDataHistorySyncResult:
    status: str
    symbol: str
    created: int = 0
    reason: str | None = None
    retry_at: str | None = None


__all__ = ["MarketDataHistorySyncResult"]
