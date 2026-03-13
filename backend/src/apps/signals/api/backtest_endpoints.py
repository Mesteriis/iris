from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.signals.api.contracts import BacktestSummaryRead, CoinBacktestsRead
from src.apps.signals.api.deps import SignalQueryDep
from src.apps.signals.api.errors import coin_not_found_error, signal_error_responses
from src.apps.signals.api.presenters import backtest_summary_read, coin_backtests_read

router = APIRouter(tags=["signals:backtests"])


@router.get("/backtests", response_model=list[BacktestSummaryRead], summary="List signal backtests")
async def read_backtests(
    service: SignalQueryDep,
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[BacktestSummaryRead]:
    items = await service.list_backtests(
        symbol=symbol,
        timeframe=timeframe,
        signal_type=signal_type,
        lookback_days=lookback_days,
        limit=limit,
    )
    return [backtest_summary_read(item) for item in items]


@router.get("/backtests/top", response_model=list[BacktestSummaryRead], summary="List top signal backtests")
async def read_top_backtests(
    service: SignalQueryDep,
    timeframe: int | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[BacktestSummaryRead]:
    items = await service.list_top_backtests(
        timeframe=timeframe,
        lookback_days=lookback_days,
        limit=limit,
    )
    return [backtest_summary_read(item) for item in items]


@router.get(
    "/coins/{symbol}/backtests",
    response_model=CoinBacktestsRead,
    summary="Read coin backtest summary",
    responses=signal_error_responses(404),
)
async def read_coin_backtests(
    symbol: str,
    service: SignalQueryDep,
    timeframe: int | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=50, ge=1, le=200),
) -> CoinBacktestsRead:
    item = await service.get_coin_backtests(
        symbol,
        timeframe=timeframe,
        signal_type=signal_type,
        lookback_days=lookback_days,
        limit=limit,
    )
    if item is None:
        raise coin_not_found_error(symbol)
    return coin_backtests_read(item)
