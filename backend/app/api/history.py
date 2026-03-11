from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.price_history import PriceHistoryCreate, PriceHistoryRead
from app.services.history_loader import (
    create_price_history,
    get_coin_by_symbol,
    list_price_history,
)

router = APIRouter(tags=["history"])


@router.get("/coins/{symbol}/history", response_model=list[PriceHistoryRead])
def read_coin_history(
    symbol: str,
    interval: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PriceHistoryRead]:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return list(list_price_history(db, coin.symbol, interval))


@router.post(
    "/coins/{symbol}/history",
    response_model=PriceHistoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_coin_history(
    symbol: str,
    payload: PriceHistoryCreate,
    db: Session = Depends(get_db),
) -> PriceHistoryRead:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    try:
        return create_price_history(db, coin, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
