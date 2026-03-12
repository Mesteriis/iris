from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.signals.schemas import (
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
from app.apps.signals.services import (
    get_coin_backtests_async,
    get_coin_decision_async,
    get_coin_final_signal_async,
    get_coin_market_decision_async,
    list_backtests_async,
    list_decisions_async,
    list_enriched_signals_async,
    list_final_signals_async,
    list_market_decisions_async,
    list_strategies_async,
    list_strategy_performance_async,
    list_top_backtests_async,
    list_top_decisions_async,
    list_top_final_signals_async,
    list_top_market_decisions_async,
    list_top_signals_async,
)
from app.core.db.session import get_db

router = APIRouter(tags=["signals"])


@router.get("/signals", response_model=list[SignalRead])
async def read_signals(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[SignalRead]:
    return list(await list_enriched_signals_async(db, symbol=symbol, timeframe=timeframe, limit=limit))


@router.get("/signals/top", response_model=list[SignalRead])
async def read_top_signals(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[SignalRead]:
    return list(await list_top_signals_async(db, limit=limit))


@router.get("/decisions", response_model=list[InvestmentDecisionRead])
async def read_decisions(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[InvestmentDecisionRead]:
    return list(await list_decisions_async(db, symbol=symbol, timeframe=timeframe, limit=limit))


@router.get("/decisions/top", response_model=list[InvestmentDecisionRead])
async def read_top_decisions(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[InvestmentDecisionRead]:
    return list(await list_top_decisions_async(db, limit=limit))


@router.get("/coins/{symbol}/decision", response_model=CoinDecisionRead)
async def read_coin_decision(symbol: str, db: AsyncSession = Depends(get_db)) -> CoinDecisionRead:
    payload = await get_coin_decision_async(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinDecisionRead.model_validate(payload)


@router.get("/market-decisions", response_model=list[MarketDecisionRead])
async def read_market_decisions(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[MarketDecisionRead]:
    return list(await list_market_decisions_async(db, symbol=symbol, timeframe=timeframe, limit=limit))


@router.get("/market-decisions/top", response_model=list[MarketDecisionRead])
async def read_top_market_decisions(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[MarketDecisionRead]:
    return list(await list_top_market_decisions_async(db, limit=limit))


@router.get("/coins/{symbol}/market-decision", response_model=CoinMarketDecisionRead)
async def read_coin_market_decision(symbol: str, db: AsyncSession = Depends(get_db)) -> CoinMarketDecisionRead:
    payload = await get_coin_market_decision_async(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinMarketDecisionRead.model_validate(payload)


@router.get("/final-signals", response_model=list[FinalSignalRead])
async def read_final_signals(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[FinalSignalRead]:
    return list(await list_final_signals_async(db, symbol=symbol, timeframe=timeframe, limit=limit))


@router.get("/final-signals/top", response_model=list[FinalSignalRead])
async def read_top_final_signals(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[FinalSignalRead]:
    return list(await list_top_final_signals_async(db, limit=limit))


@router.get("/coins/{symbol}/final-signal", response_model=CoinFinalSignalRead)
async def read_coin_final_signal(symbol: str, db: AsyncSession = Depends(get_db)) -> CoinFinalSignalRead:
    payload = await get_coin_final_signal_async(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinFinalSignalRead.model_validate(payload)


@router.get("/backtests", response_model=list[BacktestSummaryRead])
async def read_backtests(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[BacktestSummaryRead]:
    return list(
        await list_backtests_async(
            db,
            symbol=symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            lookback_days=lookback_days,
            limit=limit,
        )
    )


@router.get("/backtests/top", response_model=list[BacktestSummaryRead])
async def read_top_backtests(
    timeframe: int | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[BacktestSummaryRead]:
    return list(
        await list_top_backtests_async(
            db,
            timeframe=timeframe,
            lookback_days=lookback_days,
            limit=limit,
        )
    )


@router.get("/coins/{symbol}/backtests", response_model=CoinBacktestsRead)
async def read_coin_backtests(
    symbol: str,
    timeframe: int | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> CoinBacktestsRead:
    payload = await get_coin_backtests_async(
        db,
        symbol,
        timeframe=timeframe,
        signal_type=signal_type,
        lookback_days=lookback_days,
        limit=limit,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinBacktestsRead.model_validate(payload)


@router.get("/strategies", response_model=list[StrategyRead])
async def read_strategies(
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[StrategyRead]:
    return list(await list_strategies_async(db, enabled_only=enabled_only, limit=limit))


@router.get("/strategies/performance", response_model=list[StrategyPerformanceRead])
async def read_strategy_performance(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[StrategyPerformanceRead]:
    return list(await list_strategy_performance_async(db, limit=limit))
