from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.market_data.query_services import MarketDataQueryService
from src.apps.patterns.query_services import PatternQueryService
from src.apps.portfolio.query_services import PortfolioQueryService
from src.apps.predictions.query_services import PredictionQueryService
from src.apps.signals.query_services import SignalQueryService
from src.apps.system.api.deps import SystemStatusFacade, get_system_status_facade
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

_SIGNAL_LIMIT = 40
_TOP_SIGNAL_LIMIT = 12
_TOP_MARKET_DECISION_LIMIT = 12
_STRATEGY_LIMIT = 40
_STRATEGY_PERFORMANCE_LIMIT = 12
_TOP_BACKTEST_LIMIT = 10
_DISCOVERED_PATTERN_LIMIT = 24
_MARKET_RADAR_LIMIT = 8
_MARKET_FLOW_LIMIT = 8
_MARKET_FLOW_TIMEFRAME = 60
_PREDICTION_LIMIT = 24
_PORTFOLIO_POSITION_LIMIT = 40
_PORTFOLIO_ACTION_LIMIT = 40


@dataclass(slots=True, frozen=True)
class FrontendShellSnapshotPayload:
    coins: tuple[object, ...]
    status: object


@dataclass(slots=True, frozen=True)
class FrontendDashboardSnapshotPayload:
    coins: tuple[object, ...]
    metrics: tuple[object, ...]
    signals: tuple[object, ...]
    top_signals: tuple[object, ...]
    market_decisions: tuple[object, ...]
    patterns: tuple[object, ...]
    strategies: tuple[object, ...]
    strategy_performance: tuple[object, ...]
    top_backtests: tuple[object, ...]
    pattern_features: tuple[object, ...]
    discovered_patterns: tuple[object, ...]
    sectors: tuple[object, ...]
    sector_payload: object
    market_cycles: tuple[object, ...]
    market_radar: object
    market_flow: object
    predictions: tuple[object, ...]
    portfolio_state: object
    portfolio_positions: tuple[object, ...]
    portfolio_actions: tuple[object, ...]
    status: object


@dataclass(slots=True, frozen=True)
class FrontendReadFacade:
    market_data: MarketDataQueryService
    indicators: IndicatorQueryService
    patterns: PatternQueryService
    signals: SignalQueryService
    predictions: PredictionQueryService
    portfolio: PortfolioQueryService
    system: SystemStatusFacade

    async def get_shell_snapshot(self, *, worker_processes: list[object]) -> FrontendShellSnapshotPayload:
        return FrontendShellSnapshotPayload(
            coins=await self.market_data.list_coins(),
            status=await self.system.get_status(worker_processes=worker_processes),
        )

    async def get_dashboard_snapshot(self, *, worker_processes: list[object]) -> FrontendDashboardSnapshotPayload:
        return FrontendDashboardSnapshotPayload(
            coins=await self.market_data.list_coins(),
            metrics=await self.indicators.list_coin_metrics(),
            signals=await self.signals.list_signals(limit=_SIGNAL_LIMIT),
            top_signals=await self.signals.list_top_signals(limit=_TOP_SIGNAL_LIMIT),
            market_decisions=await self.signals.list_top_market_decisions(limit=_TOP_MARKET_DECISION_LIMIT),
            patterns=await self.patterns.list_patterns(),
            strategies=await self.signals.list_strategies(limit=_STRATEGY_LIMIT, enabled_only=False),
            strategy_performance=await self.signals.list_strategy_performance(limit=_STRATEGY_PERFORMANCE_LIMIT),
            top_backtests=await self.signals.list_top_backtests(limit=_TOP_BACKTEST_LIMIT),
            pattern_features=await self.patterns.list_pattern_features(),
            discovered_patterns=await self.patterns.list_discovered_patterns(limit=_DISCOVERED_PATTERN_LIMIT),
            sectors=await self.patterns.list_sectors(),
            sector_payload=await self.patterns.list_sector_metrics(timeframe=None),
            market_cycles=await self.patterns.list_market_cycles(symbol=None, timeframe=None),
            market_radar=await self.indicators.get_market_radar(limit=_MARKET_RADAR_LIMIT),
            market_flow=await self.indicators.get_market_flow(
                limit=_MARKET_FLOW_LIMIT,
                timeframe=_MARKET_FLOW_TIMEFRAME,
            ),
            predictions=await self.predictions.list_predictions(limit=_PREDICTION_LIMIT),
            portfolio_state=await self.portfolio.get_state(),
            portfolio_positions=await self.portfolio.list_positions(limit=_PORTFOLIO_POSITION_LIMIT),
            portfolio_actions=await self.portfolio.list_actions(limit=_PORTFOLIO_ACTION_LIMIT),
            status=await self.system.get_status(worker_processes=worker_processes),
        )


def get_frontend_read_facade(
    uow: Annotated[BaseAsyncUnitOfWork, Depends(get_uow)],
    system: Annotated[SystemStatusFacade, Depends(get_system_status_facade)],
) -> FrontendReadFacade:
    return FrontendReadFacade(
        market_data=MarketDataQueryService(uow.session),
        indicators=IndicatorQueryService(uow.session),
        patterns=PatternQueryService(uow.session),
        signals=SignalQueryService(uow.session),
        predictions=PredictionQueryService(uow.session),
        portfolio=PortfolioQueryService(uow.session),
        system=system,
    )


FrontendReadDep = Annotated[FrontendReadFacade, Depends(get_frontend_read_facade)]

__all__ = [
    "FrontendDashboardSnapshotPayload",
    "FrontendReadDep",
    "FrontendReadFacade",
    "FrontendShellSnapshotPayload",
    "get_frontend_read_facade",
]
