from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class AnomalyDetectionBatchResult:
    status: str
    created: int = 0
    items: tuple[dict[str, Any], ...] = ()
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class AnomalyEnrichmentResult:
    status: str
    anomaly_id: int
    portfolio_relevant: bool = False
    market_wide: bool = False
    reason: str | None = None


__all__ = ["AnomalyDetectionBatchResult", "AnomalyEnrichmentResult"]
