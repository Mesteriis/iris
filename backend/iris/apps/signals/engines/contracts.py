from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class SignalSuccessRate:
    pattern_slug: str
    market_regime: str
    success_rate: float


@dataclass(slots=True, frozen=True)
class SignalFusionSignalInput:
    signal_type: str
    confidence: float
    priority_score: float | None
    context_score: float | None
    regime_alignment: float | None
    candle_timestamp: datetime


@dataclass(slots=True, frozen=True)
class SignalFusionNewsImpactInput:
    item_count: int
    bullish_score: float
    bearish_score: float
    latest_timestamp: datetime


@dataclass(slots=True, frozen=True)
class SignalFusionFeatureScore:
    name: str
    value: float


@dataclass(slots=True, frozen=True)
class SignalFusionExplainability:
    dominant_factors: tuple[str, ...]
    threshold_crossings: tuple[str, ...]
    feature_scores: tuple[SignalFusionFeatureScore, ...]
    policy_path: str


@dataclass(slots=True, frozen=True)
class SignalFusionInput:
    signals: tuple[SignalFusionSignalInput, ...]
    regime: str | None
    success_rates: tuple[SignalSuccessRate, ...]
    bullish_alignment: float
    bearish_alignment: float
    news_impact: SignalFusionNewsImpactInput | None = None


@dataclass(slots=True, frozen=True)
class SignalFusionEngineResult:
    decision: str
    confidence: float
    signal_count: int
    regime: str | None
    bullish_score: float
    bearish_score: float
    agreement: float
    latest_timestamp: datetime
    news_item_count: int = 0
    news_bullish_score: float = 0.0
    news_bearish_score: float = 0.0
    explainability: SignalFusionExplainability | None = None


@dataclass(slots=True, frozen=True)
class SignalHistorySignalInput:
    coin_id: int
    timeframe: int
    signal_type: str
    confidence: float
    market_regime: str | None
    candle_timestamp: datetime


@dataclass(slots=True, frozen=True)
class SignalHistoryCandleInput:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None


@dataclass(slots=True, frozen=True)
class SignalHistoryEvaluation:
    coin_id: int
    timeframe: int
    signal_type: str
    confidence: float
    market_regime: str | None
    candle_timestamp: datetime
    profit_after_24h: float | None
    profit_after_72h: float | None
    maximum_drawdown: float | None
    result_return: float | None
    result_drawdown: float | None
    evaluated_at: datetime | None


__all__ = [
    "SignalFusionEngineResult",
    "SignalFusionExplainability",
    "SignalFusionFeatureScore",
    "SignalFusionInput",
    "SignalFusionNewsImpactInput",
    "SignalFusionSignalInput",
    "SignalHistoryCandleInput",
    "SignalHistoryEvaluation",
    "SignalHistorySignalInput",
    "SignalSuccessRate",
]
