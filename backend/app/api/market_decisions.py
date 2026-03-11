from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market_decision import CoinMarketDecisionRead, MarketDecisionRead
from app.services.market_decisions_service import (
    get_coin_market_decision,
    list_market_decisions,
    list_top_market_decisions,
)

router = APIRouter(tags=["market-decisions"])


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
def read_coin_market_decision(
    symbol: str,
    db: Session = Depends(get_db),
) -> CoinMarketDecisionRead:
    payload = get_coin_market_decision(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinMarketDecisionRead.model_validate(payload)
