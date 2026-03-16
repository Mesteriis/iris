from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from iris.apps.patterns.engines.contracts import PatternSignalInsertSpec


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


@dataclass(slots=True, frozen=True)
class PatternBootstrapCoinResult:
    status: str
    coin_id: int | None = None
    symbol: str | None = None
    detections: int = 0
    created: int = 0
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class PatternBootstrapScanResult:
    status: str
    coins: int = 0
    created: int = 0
    items: tuple[PatternBootstrapCoinResult, ...] = ()
    reason: str | None = None
    symbol: str | None = None


@dataclass(slots=True, frozen=True)
class PatternEvaluationRunResult:
    status: str
    signal_history: Mapping[str, object]
    statistics: Mapping[str, object]
    context: Mapping[str, object]
    decisions: Mapping[str, object]
    final_signals: Mapping[str, object]


@dataclass(slots=True, frozen=True)
class PatternSignalContextRefreshResult:
    status: str
    coin_id: int
    timeframe: int
    signals: int = 0
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class PatternFeatureSnapshotResult:
    coin_id: int
    timeframe: int
    timestamp: datetime | str
    price_current: float | None = None
    rsi_14: float | None = None
    macd: float | None = None


@dataclass(slots=True, frozen=True)
class PatternSignalContextRunResult:
    status: str
    context: PatternSignalContextRefreshResult
    decision: Mapping[str, object]
    final_signal: Mapping[str, object]
    feature_snapshot: PatternFeatureSnapshotResult


@dataclass(slots=True, frozen=True)
class PatternMarketStructureRefreshResult:
    status: str
    sectors: Mapping[str, object]
    cycles: Mapping[str, object]
    context: Mapping[str, object]
    decisions: Mapping[str, object]
    final_signals: Mapping[str, object]


@dataclass(slots=True, frozen=True)
class PatternDiscoveryRefreshResult:
    status: str
    patterns: int = 0
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class PatternStrategyRefreshResult:
    status: str
    strategies: Mapping[str, object]
    decisions: Mapping[str, object]
    final_signals: Mapping[str, object]


__all__ = [
    "PatternBootstrapCoinResult",
    "PatternBootstrapScanResult",
    "PatternDiscoveryRefreshResult",
    "PatternEvaluationRunResult",
    "PatternFeatureSnapshotResult",
    "PatternIncrementalDetectionStepResult",
    "PatternIncrementalSignalsResult",
    "PatternMarketCycleUpdateResult",
    "PatternMarketStructureRefreshResult",
    "PatternRegimeRefreshResult",
    "PatternSignalContextRefreshResult",
    "PatternSignalContextRunResult",
    "PatternSignalDerivationResult",
    "PatternStrategyRefreshResult",
]
