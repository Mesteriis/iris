from __future__ import annotations

from fastapi import APIRouter, status

from src.apps.market_data.api.contracts import CoinCreate, CoinRead, PriceHistoryCreate, PriceHistoryRead
from src.apps.market_data.api.deps import MarketDataCommandDep, MarketDataQueryDep
from src.apps.market_data.api.errors import (
    MarketDataCoinConflictError,
    MarketDataCoinNotFoundError,
    market_data_error_responses,
    market_data_error_to_http,
)
from src.apps.market_data.api.presenters import coin_read, price_history_read
from src.core.http.command_executor import execute_command, execute_command_no_content
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["market-data:commands"])


@router.post(
    "/coins",
    response_model=CoinRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a coin",
    responses=market_data_error_responses(409),
)
async def create_coin_endpoint(
    payload: CoinCreate,
    commands: MarketDataCommandDep,
    query_service: MarketDataQueryDep,
    request_locale: RequestLocaleDep,
) -> CoinRead:
    async def action() -> CoinRead:
        if await query_service.get_coin_read_by_symbol(payload.symbol) is not None:
            raise MarketDataCoinConflictError(payload.symbol)
        commands.backfill_trigger.schedule_after_commit(commands.uow)
        return await commands.service.create_coin(payload)

    return await execute_command(
        action=action,
        uow=commands.uow,
        presenter=coin_read,
        translate_error=lambda exc: market_data_error_to_http(exc, locale=request_locale),
    )


@router.delete(
    "/coins/{symbol}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a coin",
    responses=market_data_error_responses(404),
)
async def delete_coin_endpoint(
    symbol: str,
    commands: MarketDataCommandDep,
    request_locale: RequestLocaleDep,
) -> None:
    async def action() -> object:
        deleted = await commands.service.delete_coin(symbol)
        if not deleted:
            raise MarketDataCoinNotFoundError(symbol)
        return {"deleted": True}

    await execute_command_no_content(
        action=action,
        uow=commands.uow,
        translate_error=lambda exc: market_data_error_to_http(exc, locale=request_locale),
    )


@router.post(
    "/coins/{symbol}/history",
    response_model=PriceHistoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create coin history row",
    responses=market_data_error_responses(400, 404),
)
async def create_coin_history(
    symbol: str,
    payload: PriceHistoryCreate,
    commands: MarketDataCommandDep,
    query_service: MarketDataQueryDep,
    request_locale: RequestLocaleDep,
) -> PriceHistoryRead:
    async def action() -> PriceHistoryRead:
        coin = await query_service.get_coin_read_by_symbol(symbol)
        if coin is None:
            raise MarketDataCoinNotFoundError(symbol)
        item = await commands.service.create_price_history(symbol=str(coin.symbol), payload=payload)
        if item is None:
            raise MarketDataCoinNotFoundError(symbol)
        return item

    return await execute_command(
        action=action,
        uow=commands.uow,
        presenter=price_history_read,
        translate_error=lambda exc: market_data_error_to_http(exc, locale=request_locale),
    )
