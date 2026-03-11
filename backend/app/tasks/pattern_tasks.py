from __future__ import annotations

from app.db.session import SessionLocal
from app.patterns.engine import PatternEngine
from app.services.history_loader import get_coin_by_symbol, list_coins_ready_for_latest_sync
from app.taskiq.broker import broker
from app.taskiq.locks import redis_task_lock

PATTERN_BOOTSTRAP_LOCK_TIMEOUT_SECONDS = 7200
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
