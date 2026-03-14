from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.apps.signals.engines.contracts import SignalFusionExplainability


@dataclass(slots=True, frozen=True)
class SignalDecisionCacheSnapshot:
    coin_id: int
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None
    created_at: datetime | None


@dataclass(slots=True, frozen=True)
class SignalFusionPendingEvent:
    event_type: str
    payload: dict[str, object]


@dataclass(slots=True, frozen=True)
class SignalFusionResult:
    status: str
    coin_id: int
    timeframe: int
    reason: str | None = None
    decision_id: int | None = None
    decision: str | None = None
    confidence: float | None = None
    signal_count: int = 0
    regime: str | None = None
    news_item_count: int = 0
    news_bullish_score: float = 0.0
    news_bearish_score: float = 0.0
    explainability: SignalFusionExplainability | None = None
    cache_snapshot: SignalDecisionCacheSnapshot | None = None
    pending_events: tuple[SignalFusionPendingEvent, ...] = ()


@dataclass(slots=True, frozen=True)
class SignalFusionBatchResult:
    status: str
    coin_id: int
    timeframes: tuple[int, ...]
    items: tuple[SignalFusionResult, ...]
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class SignalHistoryRefreshResult:
    status: str
    rows: int
    evaluated: int
    coin_id: int | None
    timeframe: int | None


__all__ = [
    "SignalDecisionCacheSnapshot",
    "SignalFusionBatchResult",
    "SignalFusionPendingEvent",
    "SignalFusionResult",
    "SignalHistoryRefreshResult",
]
