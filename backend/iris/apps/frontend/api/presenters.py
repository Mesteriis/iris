from typing import Any

from iris.apps.frontend.api.contracts import FrontendDashboardSnapshotRead, FrontendShellSnapshotRead
from iris.apps.indicators.api.presenters import (
    coin_metrics_read,
    market_cycle_read,
    market_flow_read,
    market_radar_read,
)
from iris.apps.market_data.api.presenters import coin_read
from iris.apps.patterns.api.presenters import (
    discovered_pattern_read,
    pattern_feature_read,
    pattern_read,
    sector_metrics_response,
    sector_read,
)
from iris.apps.portfolio.api.presenters import portfolio_action_read, portfolio_position_read, portfolio_state_read
from iris.apps.predictions.api.presenters import prediction_read
from iris.apps.signals.api.presenters import (
    backtest_summary_read,
    market_decision_read,
    signal_read,
    strategy_performance_read,
    strategy_read,
)
from iris.apps.system.api.presenters import system_status_read


def frontend_shell_snapshot_read(item: Any) -> FrontendShellSnapshotRead:
    return FrontendShellSnapshotRead.model_validate(
        {
            "coins": [coin_read(row) for row in item.coins],
            "status": system_status_read(item.status),
        }
    )


def frontend_dashboard_snapshot_read(item: Any) -> FrontendDashboardSnapshotRead:
    return FrontendDashboardSnapshotRead.model_validate(
        {
            "coins": [coin_read(row) for row in item.coins],
            "metrics": [coin_metrics_read(row) for row in item.metrics],
            "signals": [signal_read(row) for row in item.signals],
            "top_signals": [signal_read(row) for row in item.top_signals],
            "market_decisions": [market_decision_read(row) for row in item.market_decisions],
            "patterns": [pattern_read(row) for row in item.patterns],
            "strategies": [strategy_read(row) for row in item.strategies],
            "strategy_performance": [strategy_performance_read(row) for row in item.strategy_performance],
            "top_backtests": [backtest_summary_read(row) for row in item.top_backtests],
            "pattern_features": [pattern_feature_read(row) for row in item.pattern_features],
            "discovered_patterns": [discovered_pattern_read(row) for row in item.discovered_patterns],
            "sectors": [sector_read(row) for row in item.sectors],
            "sector_payload": sector_metrics_response(item.sector_payload),
            "market_cycles": [market_cycle_read(row) for row in item.market_cycles],
            "market_radar": market_radar_read(item.market_radar),
            "market_flow": market_flow_read(item.market_flow),
            "predictions": [prediction_read(row) for row in item.predictions],
            "portfolio_state": portfolio_state_read(item.portfolio_state),
            "portfolio_positions": [portfolio_position_read(row) for row in item.portfolio_positions],
            "portfolio_actions": [portfolio_action_read(row) for row in item.portfolio_actions],
            "status": system_status_read(item.status),
        }
    )


__all__ = ["frontend_dashboard_snapshot_read", "frontend_shell_snapshot_read"]
