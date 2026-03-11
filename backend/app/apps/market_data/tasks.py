from __future__ import annotations

from app.core.db.session import SessionLocal
from app.apps.patterns.services import PatternEngine
from app.apps.market_data.services import (
    get_coin_by_symbol,
    get_next_pending_backfill_due_at,
    list_coins_pending_backfill,
    list_coins_ready_for_latest_sync,
    sync_coin_history_backfill,
    sync_coin_history_backfill_forced,
    sync_coin_latest_history,
    sync_watched_assets,
)
from app.runtime.orchestration.broker import broker
from app.runtime.orchestration.locks import redis_task_lock

HISTORY_BACKFILL_LOCK_TIMEOUT_SECONDS = 3600
HISTORY_REFRESH_LOCK_TIMEOUT_SECONDS = 900
COIN_HISTORY_LOCK_TIMEOUT_SECONDS = 1800
_PATTERN_ENGINE = PatternEngine()


def get_next_history_backfill_due_at():
    db = SessionLocal()
    try:
        return get_next_pending_backfill_due_at(db)
    finally:
        db.close()


def _with_coin_history_lock(symbol: str):
    return redis_task_lock(
        f"iris:tasklock:history_coin:{symbol.upper()}",
        timeout=COIN_HISTORY_LOCK_TIMEOUT_SECONDS,
    )


def _sync_coin_backfill_item(db, coin, *, force: bool = False) -> dict[str, object]:
    with _with_coin_history_lock(coin.symbol) as acquired:
        if not acquired:
            return {
                "symbol": coin.symbol,
                "created": 0,
                "status": "skipped",
                "reason": "coin_history_in_progress",
            }
        result = sync_coin_history_backfill_forced(db, coin) if force else sync_coin_history_backfill(db, coin)
        if result.get("status") == "ok":
            result["patterns_bootstrap"] = _PATTERN_ENGINE.bootstrap_coin(db, coin=coin, force=force)
        return result


def _sync_coin_latest_item(db, coin, *, force: bool = False) -> dict[str, object]:
    with _with_coin_history_lock(coin.symbol) as acquired:
        if not acquired:
            return {
                "symbol": coin.symbol,
                "created": 0,
                "status": "skipped",
                "reason": "coin_history_in_progress",
            }
        return sync_coin_latest_history(db, coin, force=force)


def _run_history_backfill(*, symbol: str | None = None) -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:history_backfill",
        timeout=HISTORY_BACKFILL_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {
                "status": "skipped",
                "reason": "history_backfill_in_progress",
                "mode": "backfill",
            }

        db = SessionLocal()
        try:
            sync_watched_assets(db)
            coins = list_coins_pending_backfill(db, symbol=symbol)
            items = [_sync_coin_backfill_item(db, coin) for coin in coins]
            return {
                "status": "ok",
                "mode": "backfill",
                "coins": len(coins),
                "history_points_created": sum(int(item["created"]) for item in items),
                "items": items,
            }
        finally:
            db.close()


def _run_latest_history_sync() -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:history_refresh",
        timeout=HISTORY_REFRESH_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {
                "status": "skipped",
                "reason": "history_refresh_in_progress",
                "mode": "latest",
            }

        db = SessionLocal()
        try:
            coins = list_coins_ready_for_latest_sync(db)
            items = [_sync_coin_latest_item(db, coin) for coin in coins]
            return {
                "status": "ok",
                "mode": "latest",
                "coins": len(coins),
                "history_points_created": sum(int(item["created"]) for item in items),
                "items": items,
            }
        finally:
            db.close()


def _run_manual_coin_history_job(
    *,
    symbol: str,
    mode: str = "auto",
    force: bool = True,
) -> dict[str, object]:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"auto", "backfill", "latest"}:
        return {
            "status": "error",
            "symbol": symbol.upper(),
            "reason": f"Unsupported mode '{mode}'.",
        }

    db = SessionLocal()
    try:
        coin = get_coin_by_symbol(db, symbol)
        if coin is None:
            return {
                "status": "error",
                "symbol": symbol.upper(),
                "reason": "coin_not_found",
            }

        if normalized_mode == "backfill":
            result = _sync_coin_backfill_item(db, coin, force=force)
            return {"status": "ok", "mode": "backfill", "forced": force, **result}

        if normalized_mode == "latest":
            result = _sync_coin_latest_item(db, coin, force=force)
            return {"status": "ok", "mode": "latest", "forced": force, **result}

        if coin.history_backfill_completed_at is None:
            result = _sync_coin_backfill_item(db, coin, force=force)
            return {"status": "ok", "mode": "backfill", "forced": force, **result}

        result = _sync_coin_latest_item(db, coin, force=force)
        return {"status": "ok", "mode": "latest", "forced": force, **result}
    finally:
        db.close()


@broker.task
def bootstrap_observed_coins_history() -> dict[str, object]:
    return _run_history_backfill()


@broker.task
def backfill_observed_coins_history(symbol: str | None = None) -> dict[str, object]:
    return _run_history_backfill(symbol=symbol)


@broker.task
def refresh_observed_coins_history() -> dict[str, object]:
    return _run_latest_history_sync()


@broker.task
def run_coin_history_job(
    symbol: str,
    mode: str = "auto",
    force: bool = True,
) -> dict[str, object]:
    return _run_manual_coin_history_job(symbol=symbol, mode=mode, force=force)
