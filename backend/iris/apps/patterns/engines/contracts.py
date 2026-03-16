from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class PatternRuntimeSignalSnapshot:
    signal_type: str
    confidence: float


@dataclass(slots=True, frozen=True)
class PatternCoinMetricsSnapshot:
    trend_score: int | None
    market_regime: str | None
    resolved_regime: str | None
    volatility: float | None
    price_current: float | None
    rsi_14: float | None = None
    macd: float | None = None


@dataclass(slots=True, frozen=True)
class PatternSectorMetricSnapshot:
    sector_strength: float | None
    capital_flow: float | None


@dataclass(slots=True, frozen=True)
class PatternSignalInsertSpec:
    signal_type: str
    confidence: float
    market_regime: str | None = None


@dataclass(slots=True, frozen=True)
class PatternCycleEngineInput:
    trend_score: int | None
    regime: str | None
    volatility: float | None
    price_current: float | None
    pattern_density: int
    cluster_frequency: int
    sector_strength: float | None
    capital_flow: float | None


@dataclass(slots=True, frozen=True)
class PatternCycleComputation:
    cycle_phase: str
    confidence: float


__all__ = [
    "PatternCoinMetricsSnapshot",
    "PatternCycleComputation",
    "PatternCycleEngineInput",
    "PatternRuntimeSignalSnapshot",
    "PatternSectorMetricSnapshot",
    "PatternSignalInsertSpec",
]
