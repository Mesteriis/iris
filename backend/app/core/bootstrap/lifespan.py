from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from taskiq.receiver import Receiver

from app.apps.market_data.clients import get_market_source_carousel
from app.core.db.session import wait_for_database
from app.core.settings import get_settings
from app.runtime.orchestration.broker import broker
from app.runtime.orchestration.locks import close_task_lock_client, wait_for_redis
from app.runtime.scheduler import start_scheduler
from app.runtime.streams.messages import register_default_receivers, reset_message_bus
from app.runtime.streams.publisher import reset_event_publisher
from app.runtime.streams.runner import spawn_event_worker_processes, stop_event_worker_processes

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(wait_for_database)
    await asyncio.to_thread(wait_for_redis)
    await asyncio.to_thread(app.state.run_migrations)
    await asyncio.to_thread(register_default_receivers)

    await broker.startup()
    worker_stop_event, worker_processes = await asyncio.to_thread(spawn_event_worker_processes)
    finish_event = asyncio.Event()
    backfill_event = asyncio.Event()
    receiver = Receiver(broker=broker, run_startup=False)
    listener_task = asyncio.create_task(receiver.listen(finish_event))
    scheduler_tasks = start_scheduler(
        app,
        receiver=receiver,
        finish_event=finish_event,
        backfill_event=backfill_event,
    )

    app.state.taskiq_finish_event = finish_event
    app.state.taskiq_backfill_event = backfill_event
    app.state.taskiq_listener_task = listener_task
    app.state.taskiq_receiver = receiver
    app.state.event_worker_stop_event = worker_stop_event
    app.state.event_worker_processes = worker_processes

    try:
        yield
    finally:
        finish_event.set()
        await asyncio.gather(listener_task, *scheduler_tasks, return_exceptions=True)
        await asyncio.to_thread(stop_event_worker_processes, worker_stop_event, worker_processes)
        await broker.shutdown()
        await asyncio.to_thread(reset_message_bus)
        await asyncio.to_thread(reset_event_publisher)
        await asyncio.to_thread(close_task_lock_client)
        await asyncio.to_thread(get_market_source_carousel().close)
