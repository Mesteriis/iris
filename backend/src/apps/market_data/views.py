from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.session import get_db
from src.apps.market_data.schemas import CoinCreate, CoinRead, PriceHistoryCreate, PriceHistoryRead
from src.apps.market_data.services import (
    create_coin_async,
    create_price_history_async,
    delete_coin_async,
    get_coin_by_symbol_async,
    list_coins_async,
    list_price_history_async,
)

router = APIRouter(tags=["market-data"])


@router.get("/coins", response_model=list[CoinRead], tags=["coins"])
async def read_coins(db: AsyncSession = Depends(get_db)) -> list[CoinRead]:
    return list(await list_coins_async(db))


@router.post("/coins", response_model=CoinRead, status_code=status.HTTP_201_CREATED, tags=["coins"])
async def create_coin_endpoint(
    payload: CoinCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CoinRead:
    if await get_coin_by_symbol_async(db, payload.symbol) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Coin '{payload.symbol.upper()}' already exists.",
        )
    coin = await create_coin_async(db, payload)
    trigger = getattr(request.app.state, "taskiq_backfill_event", None)
    if trigger is not None:
        trigger.set()
    return coin


@router.delete("/coins/{symbol}", status_code=status.HTTP_204_NO_CONTENT, tags=["coins"])
async def delete_coin_endpoint(symbol: str, db: AsyncSession = Depends(get_db)) -> None:
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    await delete_coin_async(db, coin)


@router.post("/coins/{symbol}/jobs/run", status_code=status.HTTP_202_ACCEPTED, tags=["coins"])
async def run_coin_job_endpoint(
    symbol: str,
    mode: Literal["auto", "backfill", "latest"] = Query(default="auto"),
    force: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    from src.apps.market_data.tasks import run_coin_history_job

    coin = await get_coin_by_symbol_async(db, symbol)
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
async def read_coin_history(
    symbol: str,
    interval: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[PriceHistoryRead]:
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return list(await list_price_history_async(db, coin.symbol, interval))


@router.post(
    "/coins/{symbol}/history",
    response_model=PriceHistoryRead,
    status_code=status.HTTP_201_CREATED,
    tags=["history"],
)
async def create_coin_history(
    symbol: str,
    payload: PriceHistoryCreate,
    db: AsyncSession = Depends(get_db),
) -> PriceHistoryRead:
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    try:
        return await create_price_history_async(db, coin, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
