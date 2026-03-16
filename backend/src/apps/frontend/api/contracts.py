from pydantic import BaseModel

from src.apps.indicators.api.contracts import CoinMetricsRead, MarketCycleRead, MarketFlowRead, MarketRadarRead
from src.apps.market_data.api.contracts import CoinRead
from src.apps.patterns.api.contracts import (
    DiscoveredPatternRead,
    PatternFeatureRead,
    PatternRead,
    SectorMetricsResponse,
    SectorRead,
)
from src.apps.portfolio.api.contracts import PortfolioActionRead, PortfolioPositionRead, PortfolioStateRead
from src.apps.predictions.api.contracts import PredictionRead
from src.apps.signals.api.contracts import (
    BacktestSummaryRead,
    MarketDecisionRead,
    SignalRead,
    StrategyPerformanceRead,
    StrategyRead,
)
from src.apps.system.api.contracts import SystemStatusRead


class FrontendShellSnapshotRead(BaseModel):
    coins: list[CoinRead]
    status: SystemStatusRead


class FrontendDashboardSnapshotRead(BaseModel):
    coins: list[CoinRead]
    metrics: list[CoinMetricsRead]
    signals: list[SignalRead]
    top_signals: list[SignalRead]
    market_decisions: list[MarketDecisionRead]
    patterns: list[PatternRead]
    strategies: list[StrategyRead]
    strategy_performance: list[StrategyPerformanceRead]
    top_backtests: list[BacktestSummaryRead]
    pattern_features: list[PatternFeatureRead]
    discovered_patterns: list[DiscoveredPatternRead]
    sectors: list[SectorRead]
    sector_payload: SectorMetricsResponse
    market_cycles: list[MarketCycleRead]
    market_radar: MarketRadarRead
    market_flow: MarketFlowRead
    predictions: list[PredictionRead]
    portfolio_state: PortfolioStateRead
    portfolio_positions: list[PortfolioPositionRead]
    portfolio_actions: list[PortfolioActionRead]
    status: SystemStatusRead


__all__ = ["FrontendDashboardSnapshotRead", "FrontendShellSnapshotRead"]
