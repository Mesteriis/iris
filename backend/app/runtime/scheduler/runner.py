from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI
from taskiq.receiver import Receiver

from app.apps.market_data import services as market_data_services
from app.apps.market_data import tasks as market_data_tasks
from app.apps.patterns import tasks as pattern_tasks
from app.apps.portfolio import tasks as portfolio_tasks
from app.apps.predictions import tasks as prediction_tasks
from app.core.settings import get_settings
from app.runtime.orchestration.dispatcher import dispatch_task_locally

settings = get_settings()
LOGGER = logging.getLogger(__name__)


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
        await dispatch_task_locally(receiver, market_data_tasks.bootstrap_observed_coins_history)

    while not stop_event.is_set():
        next_due_at = await asyncio.to_thread(market_data_tasks.get_next_history_backfill_due_at)
        timeout: float | None = None
        if next_due_at is not None:
            timeout = max((next_due_at - market_data_services.utc_now()).total_seconds(), 0.0)

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
            await dispatch_task_locally(receiver, market_data_tasks.backfill_observed_coins_history)
            continue

        if next_due_at is None:
            continue

        LOGGER.info("Queueing pending history backfill task.")
        await dispatch_task_locally(receiver, market_data_tasks.backfill_observed_coins_history)


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
            await dispatch_task_locally(receiver, market_data_tasks.refresh_observed_coins_history)


async def schedule_pattern_statistics_refresh(receiver: Receiver, stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_pattern_statistics_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing nightly pattern statistics refresh task.")
            await dispatch_task_locally(receiver, pattern_tasks.pattern_evaluation_job)


async def schedule_market_structure_refresh(receiver: Receiver, stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_market_structure_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing market structure refresh task.")
            await dispatch_task_locally(receiver, pattern_tasks.refresh_market_structure)


async def schedule_pattern_discovery_refresh(receiver: Receiver, stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_pattern_discovery_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing pattern discovery refresh task.")
            await dispatch_task_locally(receiver, pattern_tasks.run_pattern_discovery)


async def schedule_strategy_discovery_refresh(receiver: Receiver, stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_strategy_discovery_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing strategy discovery refresh task.")
            await dispatch_task_locally(receiver, pattern_tasks.strategy_discovery_job)


async def schedule_portfolio_sync(receiver: Receiver, stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_portfolio_sync_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing portfolio sync task.")
            await dispatch_task_locally(receiver, portfolio_tasks.portfolio_sync_job)


async def schedule_prediction_evaluation(receiver: Receiver, stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_prediction_evaluation_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing prediction evaluation task.")
            await dispatch_task_locally(receiver, prediction_tasks.prediction_evaluation_job)


def start_scheduler(
    app: FastAPI,
    *,
    receiver: Receiver,
    finish_event: asyncio.Event,
    backfill_event: asyncio.Event,
) -> Sequence[asyncio.Task[Any]]:
    tasks = (
        asyncio.create_task(schedule_history_backfills(receiver, finish_event, backfill_event)),
        asyncio.create_task(enqueue_latest_price_snapshots(receiver, finish_event)),
        asyncio.create_task(schedule_pattern_statistics_refresh(receiver, finish_event)),
        asyncio.create_task(schedule_market_structure_refresh(receiver, finish_event)),
        asyncio.create_task(schedule_pattern_discovery_refresh(receiver, finish_event)),
        asyncio.create_task(schedule_strategy_discovery_refresh(receiver, finish_event)),
        asyncio.create_task(schedule_portfolio_sync(receiver, finish_event)),
        asyncio.create_task(schedule_prediction_evaluation(receiver, finish_event)),
    )
    (
        app.state.taskiq_backfill_task,
        app.state.taskiq_refresh_task,
        app.state.taskiq_pattern_stats_task,
        app.state.taskiq_market_structure_task,
        app.state.taskiq_pattern_discovery_task,
        app.state.taskiq_strategy_discovery_task,
        app.state.taskiq_portfolio_sync_task,
        app.state.taskiq_prediction_evaluation_task,
    ) = tasks
    return tasks
