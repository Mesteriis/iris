from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.db.session import get_db
from app.apps.market_data.schemas import CoinCreate, CoinRead, PriceHistoryCreate, PriceHistoryRead
from app.apps.market_data.services import (
    create_coin,
    create_price_history,
    delete_coin,
    get_coin_by_symbol,
    list_coins,
    list_price_history,
)

router = APIRouter(tags=["market-data"])


@router.get("/coins", response_model=list[CoinRead], tags=["coins"])
def read_coins(db: Session = Depends(get_db)) -> list[CoinRead]:
    return list(list_coins(db))


@router.post("/coins", response_model=CoinRead, status_code=status.HTTP_201_CREATED, tags=["coins"])
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


@router.delete("/coins/{symbol}", status_code=status.HTTP_204_NO_CONTENT, tags=["coins"])
def delete_coin_endpoint(symbol: str, db: Session = Depends(get_db)) -> None:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    delete_coin(db, coin)


@router.post("/coins/{symbol}/jobs/run", status_code=status.HTTP_202_ACCEPTED, tags=["coins"])
async def run_coin_job_endpoint(
    symbol: str,
    mode: Literal["auto", "backfill", "latest"] = Query(default="auto"),
    force: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    from app.apps.market_data.tasks import run_coin_history_job

    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )

    await run_coin_history_job.kiq(symbol=coin.symbol, mode=mode, force=force)
    return {
        "status": "queued",
        "symbol": coin.symbol,
        "mode": mode,
        "force": force,
    }


@router.get("/coins/{symbol}/history", response_model=list[PriceHistoryRead], tags=["history"])
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
    tags=["history"],
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
