from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.pattern import CoinRegimeRead, PatternRead
from app.schemas.signal import SignalRead
from app.services.patterns_service import get_coin_regimes, list_coin_patterns, list_patterns

router = APIRouter(tags=["patterns"])


@router.get("/patterns", response_model=list[PatternRead])
def read_patterns(db: Session = Depends(get_db)) -> list[PatternRead]:
    return list(list_patterns(db))


@router.get("/coins/{symbol}/patterns", response_model=list[SignalRead])
def read_coin_patterns(
    symbol: str,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[SignalRead]:
    return list(list_coin_patterns(db, symbol, limit=limit))


@router.get("/coins/{symbol}/regime", response_model=CoinRegimeRead)
def read_coin_regime(symbol: str, db: Session = Depends(get_db)) -> CoinRegimeRead:
    payload = get_coin_regimes(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinRegimeRead.model_validate(payload)
