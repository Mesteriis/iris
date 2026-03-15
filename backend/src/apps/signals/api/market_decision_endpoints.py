from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from src.apps.signals.api.contracts import CoinMarketDecisionRead, MarketDecisionRead
from src.apps.signals.api.deps import SignalQueryDep
from src.apps.signals.api.errors import coin_not_found_error, signal_error_responses
from src.apps.signals.api.presenters import coin_market_decision_read, market_decision_read
from src.core.http.cache import PUBLIC_NEAR_REALTIME_CACHE, apply_conditional_cache, cache_not_modified_responses
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["signals:market-decisions"])


@router.get("/market-decisions", response_model=list[MarketDecisionRead], summary="List market decisions")
async def read_market_decisions(
    service: SignalQueryDep,
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[MarketDecisionRead]:
    items = await service.list_market_decisions(symbol=symbol, timeframe=timeframe, limit=limit)
    return [market_decision_read(item) for item in items]


@router.get("/market-decisions/top", response_model=list[MarketDecisionRead], summary="List top market decisions")
async def read_top_market_decisions(
    service: SignalQueryDep,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[MarketDecisionRead]:
    items = await service.list_top_market_decisions(limit=limit)
    return [market_decision_read(item) for item in items]


@router.get(
    "/coins/{symbol}/market-decision",
    response_model=CoinMarketDecisionRead,
    summary="Read coin market decision summary",
    responses={**signal_error_responses(404), **cache_not_modified_responses()},
)
async def read_coin_market_decision(
    symbol: str,
    request: Request,
    response: Response,
    service: SignalQueryDep,
    request_locale: RequestLocaleDep,
) -> CoinMarketDecisionRead | Response:
    item = await service.get_coin_market_decision(symbol)
    if item is None:
        raise coin_not_found_error(locale=request_locale)
    payload = coin_market_decision_read(item)
    if not_modified := apply_conditional_cache(
        request=request,
        response=response,
        payload=payload,
        policy=PUBLIC_NEAR_REALTIME_CACHE,
        generated_at=payload.generated_at,
        staleness_ms=payload.staleness_ms,
    ):
        return not_modified
    return payload
