from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.signal import SignalRead
from app.services.patterns_service import list_enriched_signals, list_top_signals

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
