from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.decision import CoinDecisionRead, InvestmentDecisionRead
from app.services.decisions_service import get_coin_decision, list_decisions, list_top_decisions

router = APIRouter(tags=["decisions"])


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
def read_coin_decision(
    symbol: str,
    db: Session = Depends(get_db),
) -> CoinDecisionRead:
    payload = get_coin_decision(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinDecisionRead.model_validate(payload)
