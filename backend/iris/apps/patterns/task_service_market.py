"""Compatibility entrypoint for pattern market discovery orchestration."""

from iris.apps.patterns.task_runtime_market import (
    MIN_DISCOVERY_SAMPLE,
    PatternMarketDiscoveryMixin,
    _candidate_definitions,
    _context_from_window,
    _signal_outcome,
    _strategy_enabled,
    _window_signature,
)

__all__ = [
    "MIN_DISCOVERY_SAMPLE",
    "PatternMarketDiscoveryMixin",
    "_candidate_definitions",
    "_context_from_window",
    "_signal_outcome",
    "_strategy_enabled",
    "_window_signature",
]
