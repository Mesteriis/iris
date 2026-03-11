from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

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
    get_coin_backtests,
    get_coin_decision,
    get_coin_final_signal,
    get_coin_market_decision,
    list_backtests,
    list_decisions,
    list_enriched_signals,
    list_final_signals,
    list_market_decisions,
    list_strategies,
    list_strategy_performance,
    list_top_backtests,
    list_top_decisions,
    list_top_final_signals,
    list_top_market_decisions,
    list_top_signals,
)
from app.core.db.session import get_db

router = APIRouter(tags=["signals"])


@router.get("/signals", response_model=list[SignalRead])
def read_signals(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[SignalRead]:
    return list(list_enriched_signals(db, symbol=symbol, timeframe=timeframe, limit=limit))


@router.get("/signals/top", response_model=list[SignalRead])
def read_top_signals(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[SignalRead]:
    return list(list_top_signals(db, limit=limit))


@router.get("/decisions", response_model=list[InvestmentDecisionRead])
def read_decisions(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[InvestmentDecisionRead]:
    return list(list_decisions(db, symbol=symbol, timeframe=timeframe, limit=limit))


@router.get("/decisions/top", response_model=list[InvestmentDecisionRead])
def read_top_decisions(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[InvestmentDecisionRead]:
    return list(list_top_decisions(db, limit=limit))


@router.get("/coins/{symbol}/decision", response_model=CoinDecisionRead)
def read_coin_decision(symbol: str, db: Session = Depends(get_db)) -> CoinDecisionRead:
    payload = get_coin_decision(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinDecisionRead.model_validate(payload)


@router.get("/market-decisions", response_model=list[MarketDecisionRead])
def read_market_decisions(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[MarketDecisionRead]:
    return list(list_market_decisions(db, symbol=symbol, timeframe=timeframe, limit=limit))


@router.get("/market-decisions/top", response_model=list[MarketDecisionRead])
def read_top_market_decisions(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[MarketDecisionRead]:
    return list(list_top_market_decisions(db, limit=limit))


@router.get("/coins/{symbol}/market-decision", response_model=CoinMarketDecisionRead)
def read_coin_market_decision(symbol: str, db: Session = Depends(get_db)) -> CoinMarketDecisionRead:
    payload = get_coin_market_decision(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinMarketDecisionRead.model_validate(payload)


@router.get("/final-signals", response_model=list[FinalSignalRead])
def read_final_signals(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[FinalSignalRead]:
    return list(list_final_signals(db, symbol=symbol, timeframe=timeframe, limit=limit))


@router.get("/final-signals/top", response_model=list[FinalSignalRead])
def read_top_final_signals(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[FinalSignalRead]:
    return list(list_top_final_signals(db, limit=limit))


@router.get("/coins/{symbol}/final-signal", response_model=CoinFinalSignalRead)
def read_coin_final_signal(symbol: str, db: Session = Depends(get_db)) -> CoinFinalSignalRead:
    payload = get_coin_final_signal(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinFinalSignalRead.model_validate(payload)


@router.get("/backtests", response_model=list[BacktestSummaryRead])
def read_backtests(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[BacktestSummaryRead]:
    return list(
        list_backtests(
            db,
            symbol=symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            lookback_days=lookback_days,
            limit=limit,
        )
    )


@router.get("/backtests/top", response_model=list[BacktestSummaryRead])
def read_top_backtests(
    timeframe: int | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[BacktestSummaryRead]:
    return list(
        list_top_backtests(
            db,
            timeframe=timeframe,
            lookback_days=lookback_days,
            limit=limit,
        )
    )


@router.get("/coins/{symbol}/backtests", response_model=CoinBacktestsRead)
def read_coin_backtests(
    symbol: str,
    timeframe: int | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    lookback_days: int = Query(default=365, ge=30, le=3650),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> CoinBacktestsRead:
    payload = get_coin_backtests(
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
def read_strategies(
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[StrategyRead]:
    return list(list_strategies(db, enabled_only=enabled_only, limit=limit))


@router.get("/strategies/performance", response_model=list[StrategyPerformanceRead])
def read_strategy_performance(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[StrategyPerformanceRead]:
    return list(list_strategy_performance(db, limit=limit))
