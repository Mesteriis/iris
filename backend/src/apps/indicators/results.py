from dataclasses import dataclass
from datetime import datetime

from src.apps.indicators.analytics import INDICATOR_VERSION


@dataclass(slots=True, frozen=True)
class IndicatorMetricsUpdate:
    coin_id: int
    activity_score: float | None = None
    activity_bucket: str | None = None
    analysis_priority: int | None = None
    market_regime: str | None = None
    market_regime_details: dict[str, object] | None = None
    price_change_24h: float | None = None
    price_change_7d: float | None = None
    volatility: float | None = None


@dataclass(slots=True, frozen=True)
class IndicatorEventItem:
    coin_id: int
    timeframe: int
    timestamp: datetime
    feature_source: str
    activity_score: float | None
    activity_bucket: str | None
    analysis_priority: int | None
    market_regime: str | None
    regime_confidence: float | None
    price_change_24h: float | None
    price_change_7d: float | None
    volatility: float | None
    classic_signals: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class IndicatorEventResult:
    status: str
    coin_id: int
    symbol: str | None = None
    reason: str | None = None
    timeframes: tuple[int, ...] = ()
    indicator_version: int = INDICATOR_VERSION
    items: tuple[IndicatorEventItem, ...] = ()


@dataclass(slots=True, frozen=True)
class FeatureSnapshotCaptureResult:
    status: str
    coin_id: int
    timeframe: int
    timestamp: datetime
    reason: str | None = None
    price_current: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    trend_score: int | None = None
    volatility: float | None = None
    sector_strength: float | None = None
    market_regime: str | None = None
    cycle_phase: str | None = None
    pattern_density: int = 0
    cluster_score: float = 0.0


@dataclass(slots=True, frozen=True)
class AnalysisScheduleResult:
    should_publish: bool
    activity_bucket: str | None
    state_updated: bool


__all__ = [
    "AnalysisScheduleResult",
    "FeatureSnapshotCaptureResult",
    "IndicatorEventItem",
    "IndicatorEventResult",
    "IndicatorMetricsUpdate",
]
