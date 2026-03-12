from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError

from src.apps.market_data.query_services import MarketDataQueryService
from src.apps.market_data.schemas import CoinCreate, CoinRead, PriceHistoryCreate, PriceHistoryRead
from src.apps.market_data.services import MarketDataService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

router = APIRouter(tags=["market-data"])
DB_UOW = Depends(get_uow)


def _coin_payload(item):
    return asdict(item) if is_dataclass(item) else item


def _coin_response(item):
    try:
        return CoinRead.model_validate(_coin_payload(item))
    except ValidationError:
        return item


def _price_history_response(item):
    if isinstance(item, dict):
        return item
    try:
        return PriceHistoryRead.model_validate(item)
    except ValidationError:
        return item


async def get_coin_by_symbol_async(db: BaseAsyncUnitOfWork, symbol: str):
    return await MarketDataQueryService(db.session).get_coin_read_by_symbol(symbol)


async def list_coins_async(db: BaseAsyncUnitOfWork):
    return await MarketDataQueryService(db.session).list_coins()


async def create_coin_async(db: BaseAsyncUnitOfWork, payload: CoinCreate):
    return await MarketDataService(db).create_coin(payload)


async def delete_coin_async(db: BaseAsyncUnitOfWork, coin) -> None:
    await MarketDataService(db).delete_coin(str(coin.symbol))


async def list_price_history_async(db: BaseAsyncUnitOfWork, symbol: str, interval: str | None = None):
    return await MarketDataQueryService(db.session).list_price_history(symbol, interval)


async def create_price_history_async(db: BaseAsyncUnitOfWork, coin, payload: PriceHistoryCreate):
    return await MarketDataService(db).create_price_history(symbol=str(coin.symbol), payload=payload)


@router.get("/coins", response_model=list[CoinRead], tags=["coins"])
async def read_coins(db: BaseAsyncUnitOfWork = DB_UOW) -> list[CoinRead]:
    items = await list_coins_async(db)
    return [_coin_response(item) for item in items]


@router.post("/coins", response_model=CoinRead, status_code=status.HTTP_201_CREATED, tags=["coins"])
async def create_coin_endpoint(
    payload: CoinCreate,
    request: Request,
    db: BaseAsyncUnitOfWork = DB_UOW,
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
    return _coin_response(coin)


@router.delete("/coins/{symbol}", status_code=status.HTTP_204_NO_CONTENT, tags=["coins"])
async def delete_coin_endpoint(symbol: str, db: BaseAsyncUnitOfWork = DB_UOW) -> None:
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
    db: BaseAsyncUnitOfWork = DB_UOW,
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
    db: BaseAsyncUnitOfWork = DB_UOW,
) -> list[PriceHistoryRead]:
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    items = await list_price_history_async(db, coin.symbol, interval)
    return [_price_history_response(item) for item in items]


@router.post(
    "/coins/{symbol}/history",
    response_model=PriceHistoryRead,
    status_code=status.HTTP_201_CREATED,
    tags=["history"],
)
async def create_coin_history(
    symbol: str,
    payload: PriceHistoryCreate,
    db: BaseAsyncUnitOfWork = DB_UOW,
) -> PriceHistoryRead:
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    try:
        item = await create_price_history_async(db, coin, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _price_history_response(item)
