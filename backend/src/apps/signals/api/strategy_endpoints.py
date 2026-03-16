from fastapi import APIRouter, Query

from src.apps.signals.api.contracts import StrategyPerformanceRead, StrategyRead
from src.apps.signals.api.deps import SignalQueryDep
from src.apps.signals.api.presenters import strategy_performance_read, strategy_read

router = APIRouter(tags=["signals:strategies"])


@router.get("/strategies", response_model=list[StrategyRead], summary="List strategies")
async def read_strategies(
    service: SignalQueryDep,
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[StrategyRead]:
    items = await service.list_strategies(enabled_only=enabled_only, limit=limit)
    return [strategy_read(item) for item in items]


@router.get("/strategies/performance", response_model=list[StrategyPerformanceRead], summary="List strategy performance")
async def read_strategy_performance(
    service: SignalQueryDep,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[StrategyPerformanceRead]:
    items = await service.list_strategy_performance(limit=limit)
    return [strategy_performance_read(item) for item in items]
