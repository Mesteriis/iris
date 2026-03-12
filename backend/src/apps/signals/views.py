from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.apps.signals.query_services import SignalQueryService
from src.apps.signals.schemas import (
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
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

router = APIRouter(tags=["signals"])
DB_UOW = Depends(get_uow)


@router.get("/signals", response_model=list[SignalRead])
async def read_signals(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[SignalRead]:
    items = await SignalQueryService(uow.session).list_signals(symbol=symbol, timeframe=timeframe, limit=limit)
    return [SignalRead.model_validate(item) for item in items]


@router.get("/signals/top", response_model=list[SignalRead])
async def read_top_signals(
    limit: int = Query(default=20, ge=1, le=200),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[SignalRead]:
    items = await SignalQueryService(uow.session).list_top_signals(limit=limit)
    return [SignalRead.model_validate(item) for item in items]


@router.get("/decisions", response_model=list[InvestmentDecisionRead])
async def read_decisions(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[InvestmentDecisionRead]:
    items = await SignalQueryService(uow.session).list_decisions(symbol=symbol, timeframe=timeframe, limit=limit)
    return [InvestmentDecisionRead.model_validate(item) for item in items]


@router.get("/decisions/top", response_model=list[InvestmentDecisionRead])
async def read_top_decisions(
    limit: int = Query(default=20, ge=1, le=200),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[InvestmentDecisionRead]:
    items = await SignalQueryService(uow.session).list_top_decisions(limit=limit)
    return [InvestmentDecisionRead.model_validate(item) for item in items]


@router.get("/coins/{symbol}/decision", response_model=CoinDecisionRead)
async def read_coin_decision(symbol: str, uow: BaseAsyncUnitOfWork = DB_UOW) -> CoinDecisionRead:
    item = await SignalQueryService(uow.session).get_coin_decision(symbol)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinDecisionRead.model_validate(item)


@router.get("/market-decisions", response_model=list[MarketDecisionRead])
async def read_market_decisions(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[MarketDecisionRead]:
    items = await SignalQueryService(uow.session).list_market_decisions(symbol=symbol, timeframe=timeframe, limit=limit)
    return [MarketDecisionRead.model_validate(item) for item in items]


@router.get("/market-decisions/top", response_model=list[MarketDecisionRead])
async def read_top_market_decisions(
    limit: int = Query(default=20, ge=1, le=200),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[MarketDecisionRead]:
    items = await SignalQueryService(uow.session).list_top_market_decisions(limit=limit)
    return [MarketDecisionRead.model_validate(item) for item in items]


@router.get("/coins/{symbol}/market-decision", response_model=CoinMarketDecisionRead)
async def read_coin_market_decision(symbol: str, uow: BaseAsyncUnitOfWork = DB_UOW) -> CoinMarketDecisionRead:
    item = await SignalQueryService(uow.session).get_coin_market_decision(symbol)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinMarketDecisionRead.model_validate(item)


@router.get("/final-signals", response_model=list[FinalSignalRead])
async def read_final_signals(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[FinalSignalRead]:
    items = await SignalQueryService(uow.session).list_final_signals(symbol=symbol, timeframe=timeframe, limit=limit)
    return [FinalSignalRead.model_validate(item) for item in items]


@router.get("/final-signals/top", response_model=list[FinalSignalRead])
async def read_top_final_signals(
    limit: int = Query(default=20, ge=1, le=200),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[FinalSignalRead]:
    items = await SignalQueryService(uow.session).list_top_final_signals(limit=limit)
    return [FinalSignalRead.model_validate(item) for item in items]


@router.get("/coins/{symbol}/final-signal", response_model=CoinFinalSignalRead)
async def read_coin_final_signal(symbol: str, uow: BaseAsyncUnitOfWork = DB_UOW) -> CoinFinalSignalRead:
    item = await SignalQueryService(uow.session).get_coin_final_signal(symbol)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinFinalSignalRead.model_validate(item)


@router.get("/backtests", response_model=list[BacktestSummaryRead])
async def read_backtests(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=100, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[BacktestSummaryRead]:
    items = await SignalQueryService(uow.session).list_backtests(
        symbol=symbol,
        timeframe=timeframe,
        signal_type=signal_type,
        lookback_days=lookback_days,
        limit=limit,
    )
    return [BacktestSummaryRead.model_validate(item) for item in items]


@router.get("/backtests/top", response_model=list[BacktestSummaryRead])
async def read_top_backtests(
    timeframe: int | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=20, ge=1, le=200),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[BacktestSummaryRead]:
    items = await SignalQueryService(uow.session).list_top_backtests(
        timeframe=timeframe,
        lookback_days=lookback_days,
        limit=limit,
    )
    return [BacktestSummaryRead.model_validate(item) for item in items]


@router.get("/coins/{symbol}/backtests", response_model=CoinBacktestsRead)
async def read_coin_backtests(
    symbol: str,
    timeframe: int | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=50, ge=1, le=200),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> CoinBacktestsRead:
    item = await SignalQueryService(uow.session).get_coin_backtests(
        symbol,
        timeframe=timeframe,
        signal_type=signal_type,
        lookback_days=lookback_days,
        limit=limit,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinBacktestsRead.model_validate(item)


@router.get("/strategies", response_model=list[StrategyRead])
async def read_strategies(
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[StrategyRead]:
    items = await SignalQueryService(uow.session).list_strategies(enabled_only=enabled_only, limit=limit)
    return [StrategyRead.model_validate(item) for item in items]


@router.get("/strategies/performance", response_model=list[StrategyPerformanceRead])
async def read_strategy_performance(
    limit: int = Query(default=100, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[StrategyPerformanceRead]:
    items = await SignalQueryService(uow.session).list_strategy_performance(limit=limit)
    return [StrategyPerformanceRead.model_validate(item) for item in items]
