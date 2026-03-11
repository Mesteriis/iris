from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.signal import SignalRead
from app.services.analytics_service import list_signals

router = APIRouter(tags=["signals"])


@router.get("/signals", response_model=list[SignalRead])
def read_signals(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[SignalRead]:
    return list(list_signals(db, symbol=symbol, timeframe=timeframe, limit=limit))
