from __future__ import annotations

from app.db.session import SessionLocal
from app.patterns.context import enrich_signal_context
from app.patterns.cycle import refresh_market_cycles
from app.patterns.engine import PatternEngine
from app.patterns.narrative import refresh_sector_metrics
from app.patterns.statistics import refresh_pattern_statistics
from app.services.history_loader import get_coin_by_symbol, list_coins_ready_for_latest_sync
from app.taskiq.broker import broker
from app.taskiq.locks import redis_task_lock

PATTERN_BOOTSTRAP_LOCK_TIMEOUT_SECONDS = 7200
PATTERN_STATISTICS_LOCK_TIMEOUT_SECONDS = 7200
MARKET_STRUCTURE_LOCK_TIMEOUT_SECONDS = 7200
_ENGINE = PatternEngine()


@broker.task
def patterns_bootstrap_scan(symbol: str | None = None, force: bool = False) -> dict[str, object]:
    lock_suffix = symbol.upper() if symbol is not None else "all"
    with redis_task_lock(
        f"iris:tasklock:patterns_bootstrap:{lock_suffix}",
        timeout=PATTERN_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "patterns_bootstrap_in_progress", "symbol": lock_suffix}

        db = SessionLocal()
        try:
            if symbol is not None:
                coin = get_coin_by_symbol(db, symbol)
                if coin is None:
                    return {"status": "error", "reason": "coin_not_found", "symbol": symbol.upper()}
                result = _ENGINE.bootstrap_coin(db, coin=coin, force=force)
                return {"status": "ok", "coins": 1, "items": [result]}

            coins = list_coins_ready_for_latest_sync(db)
            items = [_ENGINE.bootstrap_coin(db, coin=coin, force=force) for coin in coins]
            return {
                "status": "ok",
                "coins": len(coins),
                "created": sum(int(item.get("created", 0)) for item in items),
                "items": items,
            }
        finally:
            db.close()


@broker.task
def update_pattern_statistics() -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:pattern_statistics_refresh",
        timeout=PATTERN_STATISTICS_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "pattern_statistics_refresh_in_progress"}

        db = SessionLocal()
        try:
            return refresh_pattern_statistics(db)
        finally:
            db.close()


@broker.task
def signal_context_enrichment(
    coin_id: int,
    timeframe: int,
    candle_timestamp: str | None = None,
) -> dict[str, object]:
    db = SessionLocal()
    try:
        return enrich_signal_context(
            db,
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            candle_timestamp=candle_timestamp,
        )
    finally:
        db.close()


@broker.task
def refresh_market_structure() -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:market_structure_refresh",
        timeout=MARKET_STRUCTURE_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "market_structure_refresh_in_progress"}

        db = SessionLocal()
        try:
            sector_result = refresh_sector_metrics(db)
            cycle_result = refresh_market_cycles(db)
            return {"status": "ok", "sectors": sector_result, "cycles": cycle_result}
        finally:
            db.close()
