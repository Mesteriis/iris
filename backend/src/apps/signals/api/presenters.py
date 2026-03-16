from typing import Any

from fastapi.encoders import jsonable_encoder

from src.apps.signals.api.contracts import (
    BacktestSummaryRead,
    CoinBacktestsRead,
    CoinDecisionRead,
    CoinFinalSignalRead,
    CoinMarketDecisionRead,
    FinalSignalRead,
    InvestmentDecisionRead,
    MarketDecisionRead,
    SignalRead,
    StrategyPerformanceRead,
    StrategyRead,
)
from src.core.http.analytics import analytical_metadata, latest_timestamp


def signal_read(item: Any) -> SignalRead:
    return SignalRead.model_validate(item)


def investment_decision_read(item: Any) -> InvestmentDecisionRead:
    return InvestmentDecisionRead.model_validate(item)


def market_decision_read(item: Any) -> MarketDecisionRead:
    return MarketDecisionRead.model_validate(item)


def final_signal_read(item: Any) -> FinalSignalRead:
    return FinalSignalRead.model_validate(item)


def coin_decision_read(item: Any) -> CoinDecisionRead:
    return CoinDecisionRead.model_validate(item)


def coin_market_decision_read(item: Any) -> CoinMarketDecisionRead:
    payload = jsonable_encoder(item)
    return CoinMarketDecisionRead.model_validate(
        {
            **payload,
            **analytical_metadata(
                source_updated_at=latest_timestamp(row.get("created_at") for row in payload.get("items", ())),
                consistency="snapshot",
                freshness_class="near_real_time",
            ),
        }
    )


def coin_final_signal_read(item: Any) -> CoinFinalSignalRead:
    return CoinFinalSignalRead.model_validate(item)


def backtest_summary_read(item: Any) -> BacktestSummaryRead:
    return BacktestSummaryRead.model_validate(item)


def coin_backtests_read(item: Any) -> CoinBacktestsRead:
    return CoinBacktestsRead.model_validate(item)


def strategy_read(item: Any) -> StrategyRead:
    return StrategyRead.model_validate(item)


def strategy_performance_read(item: Any) -> StrategyPerformanceRead:
    return StrategyPerformanceRead.model_validate(item)


__all__ = [
    "backtest_summary_read",
    "coin_backtests_read",
    "coin_decision_read",
    "coin_final_signal_read",
    "coin_market_decision_read",
    "final_signal_read",
    "investment_decision_read",
    "market_decision_read",
    "signal_read",
    "strategy_performance_read",
    "strategy_read",
]
