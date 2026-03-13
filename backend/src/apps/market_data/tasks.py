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


async def get_next_history_backfill_due_at():
    async with AsyncUnitOfWork() as uow:
        return await MarketDataQueryService(uow.session).get_next_pending_backfill_due_at()


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
    uow: BaseAsyncUnitOfWork,
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
        result = await MarketDataHistorySyncService(uow).sync_coin_history_backfill(symbol=symbol, force=force)
        if result.get("status") == "ok":
            result["patterns_bootstrap"] = await _enqueue_patterns_bootstrap(symbol=str(result["symbol"]), force=force)
        return result


async def _sync_coin_latest_item(
    uow: BaseAsyncUnitOfWork,
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
        return await MarketDataHistorySyncService(uow).sync_coin_latest_history(symbol=symbol, force=force)


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

        async with AsyncUnitOfWork() as uow:
            query_service = MarketDataQueryService(uow.session)
            await MarketDataService(uow).sync_watched_assets()
            coin_symbols = await query_service.list_coin_symbols_pending_backfill(symbol=symbol)
            items: list[dict[str, object]] = []
            for coin_symbol in coin_symbols:
                coin = await query_service.get_coin_read_by_symbol(coin_symbol)
                if coin is None:
                    continue
                items.append(await _sync_coin_backfill_item(uow, coin))
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

        async with AsyncUnitOfWork() as uow:
            query_service = MarketDataQueryService(uow.session)
            coin_symbols = await query_service.list_coin_symbols_ready_for_latest_sync()
            items: list[dict[str, object]] = []
            for coin_symbol in coin_symbols:
                coin = await query_service.get_coin_read_by_symbol(coin_symbol)
                if coin is None:
                    continue
                items.append(await _sync_coin_latest_item(uow, coin))
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

    async with AsyncUnitOfWork() as uow:
        query_service = MarketDataQueryService(uow.session)
        coin = await query_service.get_coin_read_by_symbol(symbol)
        if coin is None:
            return {
                "status": "error",
                "symbol": symbol.upper(),
                "reason": "coin_not_found",
            }

        if normalized_mode == "backfill":
            result = await _sync_coin_backfill_item(uow, coin, force=force)
            return {"status": "ok", "mode": "backfill", "forced": force, **result}

        if normalized_mode == "latest":
            result = await _sync_coin_latest_item(uow, coin, force=force)
            return {"status": "ok", "mode": "latest", "forced": force, **result}

        if coin.history_backfill_completed_at is None:
            result = await _sync_coin_backfill_item(uow, coin, force=force)
            return {"status": "ok", "mode": "backfill", "forced": force, **result}

        result = await _sync_coin_latest_item(uow, coin, force=force)
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
