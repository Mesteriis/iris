from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from taskiq.receiver import Receiver

from app.api import coins, history, metrics, signals, system
from app.core.config import get_settings
from app.db.session import wait_for_database
from app.messaging import register_default_receivers, reset_message_bus
from app.services.market_sources import get_market_source_carousel
from app.taskiq.broker import broker
from app.taskiq.dispatcher import dispatch_task_locally
from app.taskiq.locks import close_task_lock_client, wait_for_redis
from app.tasks import analytics_tasks, history_tasks  # noqa: F401
import app.tasks.pattern_tasks  # noqa: F401
from app.services.market_data import utc_now

settings = get_settings()
LOGGER = logging.getLogger(__name__)


def get_alembic_config() -> Config:
    alembic_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(alembic_path))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def run_migrations() -> None:
    command.upgrade(get_alembic_config(), "head")


async def schedule_history_backfills(
    receiver: Receiver,
    stop_event: asyncio.Event,
    trigger_event: asyncio.Event,
) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    if settings.bootstrap_history_on_startup:
        LOGGER.info("Queueing startup history backfill task.")
        await dispatch_task_locally(receiver, history_tasks.bootstrap_observed_coins_history)

    while not stop_event.is_set():
        next_due_at = await asyncio.to_thread(history_tasks.get_next_history_backfill_due_at)
        timeout: float | None = None
        if next_due_at is not None:
            timeout = max((next_due_at - utc_now()).total_seconds(), 0.0)

        stop_waiter = asyncio.create_task(stop_event.wait())
        trigger_waiter = asyncio.create_task(trigger_event.wait())
        done, pending = await asyncio.wait(
            {stop_waiter, trigger_waiter},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        if stop_event.is_set():
            break

        if trigger_waiter in done and trigger_event.is_set():
            trigger_event.clear()
            LOGGER.info("Queueing on-demand history backfill task.")
            await dispatch_task_locally(receiver, history_tasks.backfill_observed_coins_history)
            continue

        if next_due_at is None:
            continue

        LOGGER.info("Queueing pending history backfill task.")
        await dispatch_task_locally(receiver, history_tasks.backfill_observed_coins_history)


async def enqueue_latest_price_snapshots(receiver: Receiver, stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_refresh_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing incremental history refresh task.")
            await dispatch_task_locally(receiver, history_tasks.refresh_observed_coins_history)


async def dispatch_pending_analytics_events(receiver: Receiver, stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_analytics_event_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        events = await asyncio.to_thread(analytics_tasks.get_pending_new_candle_events)
        for event in events:
            LOGGER.info(
                "Queueing analytics event for coin_id=%s timeframe=%s timestamp=%s.",
                event.coin_id,
                event.timeframe,
                event.timestamp.isoformat(),
            )
            await dispatch_task_locally(
                receiver,
                analytics_tasks.handle_new_candle_event,
                event.coin_id,
                event.timeframe,
                event.timestamp.isoformat(),
            )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(wait_for_database)
    await asyncio.to_thread(wait_for_redis)
    await asyncio.to_thread(run_migrations)
    await asyncio.to_thread(register_default_receivers)

    await broker.startup()
    finish_event = asyncio.Event()
    backfill_event = asyncio.Event()
    receiver = Receiver(broker=broker, run_startup=False)
    listener_task = asyncio.create_task(receiver.listen(finish_event))
    backfill_task = asyncio.create_task(schedule_history_backfills(receiver, finish_event, backfill_event))
    refresh_task = asyncio.create_task(enqueue_latest_price_snapshots(receiver, finish_event))
    analytics_task = asyncio.create_task(dispatch_pending_analytics_events(receiver, finish_event))

    app.state.taskiq_finish_event = finish_event
    app.state.taskiq_backfill_event = backfill_event
    app.state.taskiq_listener_task = listener_task
    app.state.taskiq_receiver = receiver
    app.state.taskiq_backfill_task = backfill_task
    app.state.taskiq_refresh_task = refresh_task
    app.state.taskiq_analytics_task = analytics_task

    try:
        yield
    finally:
        finish_event.set()
        await asyncio.gather(listener_task, backfill_task, refresh_task, analytics_task, return_exceptions=True)
        await broker.shutdown()
        await asyncio.to_thread(reset_message_bus)
        await asyncio.to_thread(close_task_lock_client)
        await asyncio.to_thread(get_market_source_carousel().close)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(coins.router)
app.include_router(metrics.router)
app.include_router(signals.router)
app.include_router(history.router)


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
    )


if __name__ == "__main__":
    run()
