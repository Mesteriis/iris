from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.apps.integrations.ha.bridge.runtime import HABridgeRuntime
from src.apps.market_data.clients import get_market_source_carousel
from src.core.db.session import wait_for_database
from src.core.settings import get_settings
from src.runtime.orchestration.broker import analytics_broker, broker
from src.runtime.orchestration.locks import close_async_task_lock_client, wait_for_redis
from src.runtime.orchestration.runner import spawn_taskiq_worker_processes, stop_taskiq_worker_processes
from src.runtime.scheduler import start_scheduler
from src.runtime.streams.messages import register_default_receivers, reset_message_bus
from src.runtime.streams.publisher import reset_event_publisher
from src.runtime.streams.runner import spawn_event_worker_processes, stop_event_worker_processes

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await wait_for_database()
    await wait_for_redis()
    ha_bridge_runtime = HABridgeRuntime()
    app.state.ha_bridge_runtime = ha_bridge_runtime
    app.state.ha_bridge_service = ha_bridge_runtime.service
    # NOTE:
    # Alembic startup migration remains synchronous intentionally.
    # This runs once during service bootstrap, outside the HTTP request path.
    await asyncio.to_thread(app.state.run_migrations)
    # NOTE:
    # Console receiver registration is legacy sync infrastructure and executes
    # only during startup, outside the main request/event loop critical path.
    await asyncio.to_thread(register_default_receivers)

    await broker.startup()
    await analytics_broker.startup()
    await ha_bridge_runtime.ensure_started()
    # NOTE:
    # Worker process spawning is an infrequent process-management step kept
    # synchronous intentionally because it does not live on the request path.
    taskiq_worker_stop_event, taskiq_worker_processes = await asyncio.to_thread(spawn_taskiq_worker_processes)
    worker_stop_event, worker_processes = await asyncio.to_thread(spawn_event_worker_processes)
    finish_event = asyncio.Event()
    backfill_event = asyncio.Event()
    scheduler_tasks = start_scheduler(
        app,
        finish_event=finish_event,
        backfill_event=backfill_event,
    )

    app.state.taskiq_finish_event = finish_event
    app.state.taskiq_backfill_event = backfill_event
    app.state.taskiq_worker_stop_event = taskiq_worker_stop_event
    app.state.taskiq_worker_processes = taskiq_worker_processes
    app.state.event_worker_stop_event = worker_stop_event
    app.state.event_worker_processes = worker_processes

    try:
        yield
    finally:
        finish_event.set()
        await asyncio.gather(*scheduler_tasks, return_exceptions=True)
        await asyncio.to_thread(stop_taskiq_worker_processes, taskiq_worker_stop_event, taskiq_worker_processes)
        await asyncio.to_thread(stop_event_worker_processes, worker_stop_event, worker_processes)
        await analytics_broker.shutdown()
        await broker.shutdown()
        await ha_bridge_runtime.stop()
        await asyncio.to_thread(reset_message_bus)
        await asyncio.to_thread(reset_event_publisher)
        await close_async_task_lock_client()
        await get_market_source_carousel().close()
