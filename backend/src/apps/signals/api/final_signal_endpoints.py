from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.signals.api.contracts import CoinFinalSignalRead, FinalSignalRead
from src.apps.signals.api.deps import SignalQueryDep
from src.apps.signals.api.errors import coin_not_found_error, signal_error_responses
from src.apps.signals.api.presenters import coin_final_signal_read, final_signal_read
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["signals:final-signals"])


@router.get("/final-signals", response_model=list[FinalSignalRead], summary="List final signals")
async def read_final_signals(
    service: SignalQueryDep,
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[FinalSignalRead]:
    items = await service.list_final_signals(symbol=symbol, timeframe=timeframe, limit=limit)
    return [final_signal_read(item) for item in items]


@router.get("/final-signals/top", response_model=list[FinalSignalRead], summary="List top final signals")
async def read_top_final_signals(
    service: SignalQueryDep,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[FinalSignalRead]:
    items = await service.list_top_final_signals(limit=limit)
    return [final_signal_read(item) for item in items]


@router.get(
    "/coins/{symbol}/final-signal",
    response_model=CoinFinalSignalRead,
    summary="Read coin final signal summary",
    responses=signal_error_responses(404),
)
async def read_coin_final_signal(
    symbol: str,
    service: SignalQueryDep,
    request_locale: RequestLocaleDep,
) -> CoinFinalSignalRead:
    item = await service.get_coin_final_signal(symbol)
    if item is None:
        raise coin_not_found_error(locale=request_locale)
    return coin_final_signal_read(item)
