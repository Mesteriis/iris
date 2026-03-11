from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.final_signal import CoinFinalSignalRead, FinalSignalRead
from app.services.final_signals_service import get_coin_final_signal, list_final_signals, list_top_final_signals

router = APIRouter(tags=["final-signals"])


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
def read_coin_final_signal(
    symbol: str,
    db: Session = Depends(get_db),
) -> CoinFinalSignalRead:
    payload = get_coin_final_signal(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinFinalSignalRead.model_validate(payload)
