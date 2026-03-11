from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.backtest import BacktestSummaryRead, CoinBacktestsRead
from app.services.backtests_service import get_coin_backtests, list_backtests, list_top_backtests

router = APIRouter(tags=["backtests"])


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
