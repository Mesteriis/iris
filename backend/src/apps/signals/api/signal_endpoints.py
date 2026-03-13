from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.signals.api.contracts import SignalRead
from src.apps.signals.api.deps import SignalQueryDep
from src.apps.signals.api.presenters import signal_read

router = APIRouter(tags=["signals:read"])


@router.get("/signals", response_model=list[SignalRead], summary="List signals")
async def read_signals(
    service: SignalQueryDep,
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SignalRead]:
    items = await service.list_signals(symbol=symbol, timeframe=timeframe, limit=limit)
    return [signal_read(item) for item in items]


@router.get("/signals/top", response_model=list[SignalRead], summary="List top signals")
async def read_top_signals(
    service: SignalQueryDep,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[SignalRead]:
    items = await service.list_top_signals(limit=limit)
    return [signal_read(item) for item in items]
