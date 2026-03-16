"""Canonical reference services for ADR 0009 and the service-layer ADR package."""

from iris.apps.cross_market.cache import read_cached_correlation, read_cached_correlation_async
from iris.apps.signals.services.fusion_service import SignalFusionService
from iris.apps.signals.services.history_service import SignalHistoryService
from iris.apps.signals.services.results import (
    SignalDecisionCacheSnapshot,
    SignalFusionBatchResult,
    SignalFusionPendingEvent,
    SignalFusionResult,
    SignalHistoryRefreshResult,
)
from iris.apps.signals.services.side_effects import SignalFusionSideEffectDispatcher

__all__ = [
    "SignalDecisionCacheSnapshot",
    "SignalFusionBatchResult",
    "SignalFusionPendingEvent",
    "SignalFusionResult",
    "SignalFusionService",
    "SignalFusionSideEffectDispatcher",
    "SignalHistoryRefreshResult",
    "SignalHistoryService",
    "read_cached_correlation",
    "read_cached_correlation_async",
]
