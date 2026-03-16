from typing import Literal

from fastapi import APIRouter, Query, status

from iris.apps.market_data.api.contracts import CoinJobAcceptedRead
from iris.apps.market_data.api.deps import MarketDataJobDispatcherDep, MarketDataQueryDep
from iris.apps.market_data.api.errors import (
    market_data_coin_not_found_error,
    market_data_error_responses,
)
from iris.apps.market_data.api.presenters import coin_job_accepted_read
from iris.core.http.deps import RequestLocaleDep

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
        raise market_data_coin_not_found_error(locale=request_locale)
    dispatch_result = await dispatcher.dispatch_coin_history(symbol=coin.symbol, mode=mode, force=force)
    return coin_job_accepted_read(
        dispatch_result=dispatch_result,
        symbol=coin.symbol,
        mode=mode,
        force=force,
        locale=request_locale,
    )
