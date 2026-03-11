from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.coin import CoinCreate, CoinRead
from app.services.history_loader import create_coin, delete_coin, get_coin_by_symbol, list_coins
from app.tasks import history_tasks

router = APIRouter(prefix="/coins", tags=["coins"])


@router.get("", response_model=list[CoinRead])
def read_coins(db: Session = Depends(get_db)) -> list[CoinRead]:
    return list(list_coins(db))


@router.post("", response_model=CoinRead, status_code=status.HTTP_201_CREATED)
async def create_coin_endpoint(
    payload: CoinCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> CoinRead:
    if get_coin_by_symbol(db, payload.symbol) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Coin '{payload.symbol.upper()}' already exists.",
        )
    coin = create_coin(db, payload)
    trigger = getattr(request.app.state, "taskiq_backfill_event", None)
    if trigger is not None:
        trigger.set()
    return coin


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coin_endpoint(symbol: str, db: Session = Depends(get_db)) -> None:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    delete_coin(db, coin)


@router.post("/{symbol}/jobs/run", status_code=status.HTTP_202_ACCEPTED)
async def run_coin_job_endpoint(
    symbol: str,
    mode: Literal["auto", "backfill", "latest"] = Query(default="auto"),
    force: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )

    await history_tasks.run_coin_history_job.kiq(symbol=coin.symbol, mode=mode, force=force)
    return {
        "status": "queued",
        "symbol": coin.symbol,
        "mode": mode,
        "force": force,
    }
