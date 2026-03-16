from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.core.http.contracts import AnalyticalReadContract


class SignalRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    timeframe: int
    signal_type: str
    confidence: float
    priority_score: float = 0.0
    context_score: float = 0.0
    regime_alignment: float = 0.0
    candle_timestamp: datetime
    created_at: datetime
    market_regime: str | None = None
    cycle_phase: str | None = None
    cycle_confidence: float | None = None
    cluster_membership: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class FinalSignalRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    timeframe: int
    decision: str
    confidence: float
    risk_adjusted_score: float
    liquidity_score: float
    slippage_risk: float
    volatility_risk: float
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinFinalSignalItemRead(BaseModel):
    timeframe: int
    decision: str
    confidence: float
    risk_adjusted_score: float
    liquidity_score: float
    slippage_risk: float
    volatility_risk: float
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinFinalSignalRead(BaseModel):
    coin_id: int
    symbol: str
    canonical_decision: str | None = None
    items: list[CoinFinalSignalItemRead]

    model_config = ConfigDict(from_attributes=True)


class InvestmentDecisionRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    timeframe: int
    decision: str
    confidence: float
    score: float
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinDecisionItemRead(BaseModel):
    timeframe: int
    decision: str
    confidence: float
    score: float
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinDecisionRead(BaseModel):
    coin_id: int
    symbol: str
    canonical_decision: str | None = None
    items: list[CoinDecisionItemRead]

    model_config = ConfigDict(from_attributes=True)


class MarketDecisionRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None = None
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoinMarketDecisionItemRead(BaseModel):
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CoinMarketDecisionRead(AnalyticalReadContract):
    coin_id: int
    symbol: str
    canonical_decision: str | None = None
    items: list[CoinMarketDecisionItemRead]

    model_config = ConfigDict(from_attributes=True)


class StrategyRuleRead(BaseModel):
    pattern_slug: str
    regime: str
    sector: str
    cycle: str
    min_confidence: float

    model_config = ConfigDict(from_attributes=True)


class StrategyPerformanceRead(BaseModel):
    strategy_id: int
    name: str
    enabled: bool
    sample_size: int
    win_rate: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyRead(BaseModel):
    id: int
    name: str
    description: str
    enabled: bool
    created_at: datetime
    rules: list[StrategyRuleRead]
    performance: StrategyPerformanceRead | None = None

    model_config = ConfigDict(from_attributes=True)


class BacktestSummaryRead(BaseModel):
    symbol: str | None = None
    signal_type: str
    timeframe: int
    sample_size: int
    coin_count: int
    win_rate: float
    roi: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    avg_confidence: float
    last_evaluated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CoinBacktestsRead(BaseModel):
    coin_id: int
    symbol: str
    items: list[BacktestSummaryRead]

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "BacktestSummaryRead",
    "CoinBacktestsRead",
    "CoinDecisionRead",
    "CoinFinalSignalItemRead",
    "CoinFinalSignalRead",
    "CoinMarketDecisionItemRead",
    "CoinMarketDecisionRead",
    "FinalSignalRead",
    "InvestmentDecisionRead",
    "MarketDecisionRead",
    "SignalRead",
    "StrategyPerformanceRead",
    "StrategyRead",
    "StrategyRuleRead",
]
