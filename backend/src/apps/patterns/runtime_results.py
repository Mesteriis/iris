from __future__ import annotations

from dataclasses import dataclass

from src.apps.patterns.engines.contracts import PatternSignalInsertSpec


@dataclass(slots=True, frozen=True)
class PatternIncrementalDetectionStepResult:
    status: str
    coin_id: int
    timeframe: int
    detections: int = 0
    created: int = 0
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class PatternSignalDerivationResult:
    status: str
    created: int = 0
    reason: str | None = None
    specs: tuple[PatternSignalInsertSpec, ...] = ()


@dataclass(slots=True, frozen=True)
class PatternMarketCycleUpdateResult:
    status: str
    coin_id: int
    timeframe: int
    cycle_phase: str | None = None
    confidence: float | None = None
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class PatternIncrementalSignalsResult:
    status: str
    coin_id: int
    timeframe: int
    new_signal_types: tuple[str, ...]
    requires_commit: bool
    detection: PatternIncrementalDetectionStepResult
    clusters: PatternSignalDerivationResult
    hierarchy: PatternSignalDerivationResult


@dataclass(slots=True, frozen=True)
class PatternRegimeRefreshResult:
    status: str
    requires_commit: bool
    previous_cycle: str | None
    next_cycle: str | None
    regime: str | None
    regime_confidence: float


__all__ = [
    "PatternIncrementalDetectionStepResult",
    "PatternIncrementalSignalsResult",
    "PatternMarketCycleUpdateResult",
    "PatternRegimeRefreshResult",
    "PatternSignalDerivationResult",
]
