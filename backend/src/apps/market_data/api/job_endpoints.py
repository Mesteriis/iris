from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, status

from src.apps.market_data.api.contracts import CoinJobAcceptedRead
from src.apps.market_data.api.deps import MarketDataJobDispatcherDep, MarketDataQueryDep
from src.apps.market_data.api.errors import (
    MarketDataCoinNotFoundError,
    market_data_error_responses,
    market_data_error_to_http,
)
from src.apps.market_data.api.presenters import coin_job_accepted_read
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["market-data:jobs"])


@router.post(
    "/coins/{symbol}/jobs/run",
    response_model=CoinJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue coin history job",
    responses=market_data_error_responses(404),
)
async def run_coin_job_endpoint(
    symbol: str,
    dispatcher: MarketDataJobDispatcherDep,
    query_service: MarketDataQueryDep,
    request_locale: RequestLocaleDep,
    mode: Literal["auto", "backfill", "latest"] = Query(default="auto"),
    force: bool = Query(default=True),
) -> CoinJobAcceptedRead:
    coin = await query_service.get_coin_read_by_symbol(symbol)
    if coin is None:
        http_error = market_data_error_to_http(MarketDataCoinNotFoundError(symbol), locale=request_locale)
        assert http_error is not None
        raise http_error
    dispatch_result = await dispatcher.dispatch_coin_history(symbol=coin.symbol, mode=mode, force=force)
    return coin_job_accepted_read(
        dispatch_result=dispatch_result,
        symbol=coin.symbol,
        mode=mode,
        force=force,
        locale=request_locale,
    )
