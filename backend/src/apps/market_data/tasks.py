from __future__ import annotations

from src.apps.market_data.query_services import MarketDataQueryService
from src.apps.market_data.services import MarketDataHistorySyncService, MarketDataService
from src.apps.patterns.tasks import patterns_bootstrap_scan
from src.core.db.uow import AsyncUnitOfWork, BaseAsyncUnitOfWork
from src.runtime.orchestration.broker import broker
from src.runtime.orchestration.locks import async_redis_task_lock

HISTORY_BACKFILL_LOCK_TIMEOUT_SECONDS = 3600
HISTORY_REFRESH_LOCK_TIMEOUT_SECONDS = 900
COIN_HISTORY_LOCK_TIMEOUT_SECONDS = 1800
AsyncSessionLocal = AsyncUnitOfWork


def _session(value):
    return value.session if hasattr(value, "session") else value


async def get_next_pending_backfill_due_at_async():
    async with AsyncSessionLocal() as db:
        return await MarketDataQueryService(_session(db)).get_next_pending_backfill_due_at()


async def sync_watched_assets_async(db):
    return await MarketDataService(db).sync_watched_assets()


async def list_coin_symbols_pending_backfill_async(db, *, symbol: str | None = None):
    return await MarketDataQueryService(_session(db)).list_coin_symbols_pending_backfill(symbol=symbol)


async def list_coin_symbols_ready_for_latest_sync_async(db):
    return await MarketDataQueryService(_session(db)).list_coin_symbols_ready_for_latest_sync()


async def get_coin_by_symbol_async(db, symbol: str):
    return await MarketDataQueryService(_session(db)).get_coin_read_by_symbol(symbol)


async def sync_coin_history_backfill_async(db, coin):
    return await MarketDataHistorySyncService(db).sync_coin_history_backfill(symbol=coin.symbol, force=False)


async def sync_coin_history_backfill_forced_async(db, coin):
    return await MarketDataHistorySyncService(db).sync_coin_history_backfill(symbol=coin.symbol, force=True)


async def sync_coin_latest_history_async(db, coin, *, force: bool = False):
    return await MarketDataHistorySyncService(db).sync_coin_latest_history(symbol=coin.symbol, force=force)


async def get_next_history_backfill_due_at():
    return await get_next_pending_backfill_due_at_async()


def _with_coin_history_lock(symbol: str):
    return async_redis_task_lock(
        f"iris:tasklock:history_coin:{symbol.upper()}",
        timeout=COIN_HISTORY_LOCK_TIMEOUT_SECONDS,
    )


async def _enqueue_patterns_bootstrap(*, symbol: str, force: bool = False) -> dict[str, object]:
    await patterns_bootstrap_scan.kiq(symbol=symbol, force=force)
    return {
        "status": "queued",
        "queue": "analytics",
        "symbol": symbol.upper(),
        "force": force,
    }


async def _sync_coin_backfill_item(
    db: BaseAsyncUnitOfWork,
    coin,
    *,
    force: bool = False,
) -> dict[str, object]:
    symbol = str(coin.symbol)
    async with _with_coin_history_lock(symbol) as acquired:
        if not acquired:
            return {
                "symbol": symbol.upper(),
                "created": 0,
                "status": "skipped",
                "reason": "coin_history_in_progress",
            }
        result = await (
            sync_coin_history_backfill_forced_async(db, coin) if force else sync_coin_history_backfill_async(db, coin)
        )
        if result.get("status") == "ok":
            result["patterns_bootstrap"] = await _enqueue_patterns_bootstrap(symbol=str(result["symbol"]), force=force)
        return result


async def _sync_coin_latest_item(
    db: BaseAsyncUnitOfWork,
    coin,
    *,
    force: bool = False,
) -> dict[str, object]:
    symbol = str(coin.symbol)
    async with _with_coin_history_lock(symbol) as acquired:
        if not acquired:
            return {
                "symbol": symbol.upper(),
                "created": 0,
                "status": "skipped",
                "reason": "coin_history_in_progress",
            }
        return await sync_coin_latest_history_async(db, coin, force=force)


async def _run_history_backfill(*, symbol: str | None = None) -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:history_backfill",
        timeout=HISTORY_BACKFILL_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {
                "status": "skipped",
                "reason": "history_backfill_in_progress",
                "mode": "backfill",
            }

        async with AsyncSessionLocal() as db:
            await sync_watched_assets_async(db)
            coin_symbols = await list_coin_symbols_pending_backfill_async(db, symbol=symbol)
            items: list[dict[str, object]] = []
            for coin_symbol in coin_symbols:
                coin = await get_coin_by_symbol_async(db, coin_symbol)
                if coin is None:
                    continue
                items.append(await _sync_coin_backfill_item(db, coin))
            return {
                "status": "ok",
                "mode": "backfill",
                "coins": len(coin_symbols),
                "history_points_created": sum(int(item["created"]) for item in items),
                "items": items,
            }


async def _run_latest_history_sync() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:history_refresh",
        timeout=HISTORY_REFRESH_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {
                "status": "skipped",
                "reason": "history_refresh_in_progress",
                "mode": "latest",
            }

        async with AsyncSessionLocal() as db:
            coin_symbols = await list_coin_symbols_ready_for_latest_sync_async(db)
            items: list[dict[str, object]] = []
            for coin_symbol in coin_symbols:
                coin = await get_coin_by_symbol_async(db, coin_symbol)
                if coin is None:
                    continue
                items.append(await _sync_coin_latest_item(db, coin))
            return {
                "status": "ok",
                "mode": "latest",
                "coins": len(coin_symbols),
                "history_points_created": sum(int(item["created"]) for item in items),
                "items": items,
            }


async def _run_manual_coin_history_job(
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

    async with AsyncSessionLocal() as db:
        coin = await get_coin_by_symbol_async(db, symbol)
        if coin is None:
            return {
                "status": "error",
                "symbol": symbol.upper(),
                "reason": "coin_not_found",
            }

        if normalized_mode == "backfill":
            result = await _sync_coin_backfill_item(db, coin, force=force)
            return {"status": "ok", "mode": "backfill", "forced": force, **result}

        if normalized_mode == "latest":
            result = await _sync_coin_latest_item(db, coin, force=force)
            return {"status": "ok", "mode": "latest", "forced": force, **result}

        if coin.history_backfill_completed_at is None:
            result = await _sync_coin_backfill_item(db, coin, force=force)
            return {"status": "ok", "mode": "backfill", "forced": force, **result}

        result = await _sync_coin_latest_item(db, coin, force=force)
        return {"status": "ok", "mode": "latest", "forced": force, **result}


@broker.task
async def bootstrap_observed_coins_history() -> dict[str, object]:
    return await _run_history_backfill()


@broker.task
async def backfill_observed_coins_history(symbol: str | None = None) -> dict[str, object]:
    return await _run_history_backfill(symbol=symbol)


@broker.task
async def refresh_observed_coins_history() -> dict[str, object]:
    return await _run_latest_history_sync()


@broker.task
async def run_coin_history_job(
    symbol: str,
    mode: str = "auto",
    force: bool = True,
) -> dict[str, object]:
    return await _run_manual_coin_history_job(symbol=symbol, mode=mode, force=force)
