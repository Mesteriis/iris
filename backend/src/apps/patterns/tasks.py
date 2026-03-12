from __future__ import annotations

from src.core.db.session import AsyncSessionLocal
from src.apps.market_data.models import Coin
from src.apps.market_data.services import get_coin_by_symbol_async, list_coin_symbols_ready_for_latest_sync_async
from src.apps.patterns.services import (
    PatternEngine,
    enrich_signal_context,
    evaluate_investment_decision,
    refresh_discovered_patterns,
    refresh_investment_decisions,
    refresh_market_cycles,
    refresh_recent_signal_contexts,
    refresh_sector_metrics,
    refresh_strategies,
    run_pattern_evaluation_cycle,
)
from src.apps.patterns.domain.risk import evaluate_final_signal, refresh_final_signals
from src.runtime.orchestration.broker import analytics_broker
from src.runtime.orchestration.locks import async_redis_task_lock

PATTERN_BOOTSTRAP_LOCK_TIMEOUT_SECONDS = 7200
PATTERN_STATISTICS_LOCK_TIMEOUT_SECONDS = 7200
MARKET_STRUCTURE_LOCK_TIMEOUT_SECONDS = 7200
PATTERN_DISCOVERY_LOCK_TIMEOUT_SECONDS = 14400
STRATEGY_DISCOVERY_LOCK_TIMEOUT_SECONDS = 14400
_ENGINE = PatternEngine()


async def _run_sync_pattern_core(db, fn):
    # NOTE:
    # The pattern engine is still implemented as a large synchronous analytics
    # core. It remains synchronous intentionally while the deeper
    # domain/repository split is migrated incrementally.
    # This code runs only on the dedicated analytics TaskIQ worker queue,
    # outside the main FastAPI request/event loop critical path.
    return await db.run_sync(fn)


@analytics_broker.task
async def patterns_bootstrap_scan(symbol: str | None = None, force: bool = False) -> dict[str, object]:
    lock_suffix = symbol.upper() if symbol is not None else "all"
    async with async_redis_task_lock(
        f"iris:tasklock:patterns_bootstrap:{lock_suffix}",
        timeout=PATTERN_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "patterns_bootstrap_in_progress", "symbol": lock_suffix}

        async with AsyncSessionLocal() as db:
            if symbol is not None:
                coin = await get_coin_by_symbol_async(db, symbol)
                if coin is None:
                    return {"status": "error", "reason": "coin_not_found", "symbol": symbol.upper()}
                result = await _run_sync_pattern_core(
                    db,
                    lambda sync_db: _ENGINE.bootstrap_coin(
                        sync_db,
                        coin=sync_db.get(Coin, int(coin.id)),
                        force=force,
                    ),
                )
                return {"status": "ok", "coins": 1, "items": [result]}

            coin_symbols = await list_coin_symbols_ready_for_latest_sync_async(db)
            items = []
            for coin_symbol in coin_symbols:
                coin = await get_coin_by_symbol_async(db, coin_symbol)
                if coin is None:
                    continue
                items.append(
                    await _run_sync_pattern_core(
                        db,
                        lambda sync_db, coin_id=int(coin.id): _ENGINE.bootstrap_coin(
                            sync_db,
                            coin=sync_db.get(Coin, coin_id),
                            force=force,
                        ),
                    )
                )
            return {
                "status": "ok",
                "coins": len(coin_symbols),
                "created": sum(int(item.get("created", 0)) for item in items),
                "items": items,
            }


async def _run_pattern_evaluation() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:pattern_statistics_refresh",
        timeout=PATTERN_STATISTICS_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "pattern_statistics_refresh_in_progress"}

        async with AsyncSessionLocal() as db:
            return await _run_sync_pattern_core(db, lambda sync_db: run_pattern_evaluation_cycle(sync_db))


@analytics_broker.task
async def pattern_evaluation_job() -> dict[str, object]:
    return await _run_pattern_evaluation()


@analytics_broker.task
async def update_pattern_statistics() -> dict[str, object]:
    return await _run_pattern_evaluation()


@analytics_broker.task
async def signal_context_enrichment(
    coin_id: int,
    timeframe: int,
    candle_timestamp: str | None = None,
) -> dict[str, object]:
    async with AsyncSessionLocal() as db:
        return await _run_sync_pattern_core(
            db,
            lambda sync_db: {
                "status": "ok",
                "context": enrich_signal_context(
                    sync_db,
                    coin_id=int(coin_id),
                    timeframe=int(timeframe),
                    candle_timestamp=candle_timestamp,
                ),
                "decision": evaluate_investment_decision(
                    sync_db,
                    coin_id=int(coin_id),
                    timeframe=int(timeframe),
                    emit_event=False,
                ),
                "final_signal": evaluate_final_signal(
                    sync_db,
                    coin_id=int(coin_id),
                    timeframe=int(timeframe),
                    emit_event=False,
                ),
            },
        )


@analytics_broker.task
async def refresh_market_structure() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:market_structure_refresh",
        timeout=MARKET_STRUCTURE_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "market_structure_refresh_in_progress"}

        async with AsyncSessionLocal() as db:
            return await _run_sync_pattern_core(
                db,
                lambda sync_db: {
                    "status": "ok",
                    "sectors": refresh_sector_metrics(sync_db),
                    "cycles": refresh_market_cycles(sync_db),
                    "context": refresh_recent_signal_contexts(sync_db, lookback_days=30),
                    "decisions": refresh_investment_decisions(sync_db, lookback_days=30, emit_events=False),
                    "final_signals": refresh_final_signals(sync_db, lookback_days=30, emit_events=False),
                },
            )


@analytics_broker.task
async def run_pattern_discovery() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:pattern_discovery_refresh",
        timeout=PATTERN_DISCOVERY_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "pattern_discovery_refresh_in_progress"}

        async with AsyncSessionLocal() as db:
            return await _run_sync_pattern_core(db, lambda sync_db: refresh_discovered_patterns(sync_db))


@analytics_broker.task
async def strategy_discovery_job() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:strategy_discovery_refresh",
        timeout=STRATEGY_DISCOVERY_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "strategy_discovery_refresh_in_progress"}

        async with AsyncSessionLocal() as db:
            return await _run_sync_pattern_core(
                db,
                lambda sync_db: {
                    "status": "ok",
                    "strategies": refresh_strategies(sync_db),
                    "decisions": refresh_investment_decisions(sync_db, lookback_days=30, emit_events=False),
                    "final_signals": refresh_final_signals(sync_db, lookback_days=30, emit_events=False),
                },
            )
