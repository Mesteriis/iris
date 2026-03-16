from collections.abc import Callable
from typing import ParamSpec, TypeVar, cast

from src.apps.patterns.task_services import (
    PatternBootstrapService,
    PatternDiscoveryService,
    PatternEvaluationService,
    PatternMarketStructureService,
    PatternSignalContextService,
    PatternStrategyService,
)
from src.core.db.uow import AsyncUnitOfWork
from src.runtime.orchestration.broker import analytics_broker
from src.runtime.orchestration.locks import async_redis_task_lock

P = ParamSpec("P")
R = TypeVar("R")

PATTERN_BOOTSTRAP_LOCK_TIMEOUT_SECONDS = 7200
PATTERN_STATISTICS_LOCK_TIMEOUT_SECONDS = 7200
MARKET_STRUCTURE_LOCK_TIMEOUT_SECONDS = 7200
PATTERN_DISCOVERY_LOCK_TIMEOUT_SECONDS = 14400
STRATEGY_DISCOVERY_LOCK_TIMEOUT_SECONDS = 14400


def _analytics_task[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    return cast(Callable[P, R], analytics_broker.task(func))


async def _maybe_commit(uow: object) -> None:
    commit = getattr(uow, "commit", None)
    if callable(commit):
        await commit()


@_analytics_task
async def patterns_bootstrap_scan(symbol: str | None = None, force: bool = False) -> dict[str, object]:
    lock_suffix = symbol.upper() if symbol is not None else "all"
    async with async_redis_task_lock(
        f"iris:tasklock:patterns_bootstrap:{lock_suffix}",
        timeout=PATTERN_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "patterns_bootstrap_in_progress", "symbol": lock_suffix}

        async with AsyncUnitOfWork() as uow:
            result = await PatternBootstrapService(uow).bootstrap_scan(symbol=symbol, force=force)
            payload = result
            if payload.get("status") != "error":
                await _maybe_commit(uow)
            return payload


async def _run_pattern_evaluation() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:pattern_statistics_refresh",
        timeout=PATTERN_STATISTICS_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "pattern_statistics_refresh_in_progress"}

        async with AsyncUnitOfWork() as uow:
            result = await PatternEvaluationService(uow).run()
            await _maybe_commit(uow)
            return result


@_analytics_task
async def pattern_evaluation_job() -> dict[str, object]:
    return await _run_pattern_evaluation()


@_analytics_task
async def update_pattern_statistics() -> dict[str, object]:
    return await _run_pattern_evaluation()


@_analytics_task
async def signal_context_enrichment(
    coin_id: int,
    timeframe: int,
    candle_timestamp: str | None = None,
) -> dict[str, object]:
    async with AsyncUnitOfWork() as uow:
        result = await PatternSignalContextService(uow).enrich(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            candle_timestamp=candle_timestamp,
        )
        await _maybe_commit(uow)
        return result


@_analytics_task
async def refresh_market_structure() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:market_structure_refresh",
        timeout=MARKET_STRUCTURE_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "market_structure_refresh_in_progress"}

        async with AsyncUnitOfWork() as uow:
            result = await PatternMarketStructureService(uow).refresh()
            await _maybe_commit(uow)
            return result


@_analytics_task
async def run_pattern_discovery() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:pattern_discovery_refresh",
        timeout=PATTERN_DISCOVERY_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "pattern_discovery_refresh_in_progress"}

        async with AsyncUnitOfWork() as uow:
            result = await PatternDiscoveryService(uow).refresh()
            await _maybe_commit(uow)
            return result


@_analytics_task
async def strategy_discovery_job() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:strategy_discovery_refresh",
        timeout=STRATEGY_DISCOVERY_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "strategy_discovery_refresh_in_progress"}

        async with AsyncUnitOfWork() as uow:
            result = await PatternStrategyService(uow).refresh()
            await _maybe_commit(uow)
            return result
