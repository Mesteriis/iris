from fastapi import APIRouter, Query

from iris.apps.market_data.api.contracts import CoinRead, PriceHistoryRead
from iris.apps.market_data.api.deps import MarketDataQueryDep
from iris.apps.market_data.api.errors import market_data_coin_not_found_error, market_data_error_responses
from iris.apps.market_data.api.presenters import coin_read, price_history_read
from iris.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["market-data:read"])


@router.get("/coins", response_model=list[CoinRead], summary="List coins")
async def read_coins(service: MarketDataQueryDep) -> list[CoinRead]:
    return [coin_read(item) for item in await service.list_coins()]


@router.get(
    "/coins/{symbol}/history",
    response_model=list[PriceHistoryRead],
    summary="List coin history",
    responses=market_data_error_responses(404),
)
async def read_coin_history(
    symbol: str,
    service: MarketDataQueryDep,
    request_locale: RequestLocaleDep,
    interval: str | None = Query(default=None),
) -> list[PriceHistoryRead]:
    coin = await service.get_coin_read_by_symbol(symbol)
    if coin is None:
        raise market_data_coin_not_found_error(locale=request_locale)
    items = await service.list_price_history(coin.symbol, interval)
    return [price_history_read(item) for item in items]
