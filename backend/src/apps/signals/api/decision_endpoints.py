from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.signals.api.contracts import CoinDecisionRead, InvestmentDecisionRead
from src.apps.signals.api.deps import SignalQueryDep
from src.apps.signals.api.errors import coin_not_found_error, signal_error_responses
from src.apps.signals.api.presenters import coin_decision_read, investment_decision_read

router = APIRouter(tags=["signals:decisions"])


@router.get("/decisions", response_model=list[InvestmentDecisionRead], summary="List investment decisions")
async def read_decisions(
    service: SignalQueryDep,
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[InvestmentDecisionRead]:
    items = await service.list_decisions(symbol=symbol, timeframe=timeframe, limit=limit)
    return [investment_decision_read(item) for item in items]


@router.get("/decisions/top", response_model=list[InvestmentDecisionRead], summary="List top investment decisions")
async def read_top_decisions(
    service: SignalQueryDep,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[InvestmentDecisionRead]:
    items = await service.list_top_decisions(limit=limit)
    return [investment_decision_read(item) for item in items]


@router.get(
    "/coins/{symbol}/decision",
    response_model=CoinDecisionRead,
    summary="Read coin decision summary",
    responses=signal_error_responses(404),
)
async def read_coin_decision(symbol: str, service: SignalQueryDep) -> CoinDecisionRead:
    item = await service.get_coin_decision(symbol)
    if item is None:
        raise coin_not_found_error(symbol)
    return coin_decision_read(item)
