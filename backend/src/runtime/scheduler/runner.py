import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI

from src.apps.hypothesis_engine.tasks import hypothesis_tasks
from src.apps.market_data import services as market_data_services
from src.apps.market_data import tasks as market_data_tasks
from src.apps.market_structure import tasks as market_structure_tasks
from src.apps.news import tasks as news_tasks
from src.apps.patterns import tasks as pattern_tasks
from src.apps.portfolio import tasks as portfolio_tasks
from src.apps.predictions import tasks as prediction_tasks
from src.core.ai import hypothesis_evaluation_surfaces_enabled
from src.core.settings import get_settings
from src.runtime.orchestration.dispatcher import enqueue_task

settings = get_settings()
LOGGER = logging.getLogger(__name__)


async def schedule_history_backfills(
    stop_event: asyncio.Event,
    trigger_event: asyncio.Event,
) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    if settings.bootstrap_history_on_startup:
        LOGGER.info("Queueing startup history backfill task.")
        await enqueue_task(market_data_tasks.bootstrap_observed_coins_history)

    while not stop_event.is_set():
        next_due_at = await market_data_tasks.get_next_history_backfill_due_at()
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
            await enqueue_task(market_data_tasks.backfill_observed_coins_history)
            continue

        if next_due_at is None:
            continue

        LOGGER.info("Queueing pending history backfill task.")
        await enqueue_task(market_data_tasks.backfill_observed_coins_history)


async def enqueue_latest_price_snapshots(stop_event: asyncio.Event) -> None:
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
            await enqueue_task(market_data_tasks.refresh_observed_coins_history)


async def schedule_pattern_statistics_refresh(stop_event: asyncio.Event) -> None:
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
            await enqueue_task(pattern_tasks.pattern_evaluation_job)


async def schedule_market_structure_refresh(stop_event: asyncio.Event) -> None:
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
            await enqueue_task(pattern_tasks.refresh_market_structure)


async def schedule_pattern_discovery_refresh(stop_event: asyncio.Event) -> None:
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
            await enqueue_task(pattern_tasks.run_pattern_discovery)


async def schedule_strategy_discovery_refresh(stop_event: asyncio.Event) -> None:
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
            await enqueue_task(pattern_tasks.strategy_discovery_job)


async def schedule_portfolio_sync(stop_event: asyncio.Event) -> None:
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
            await enqueue_task(portfolio_tasks.portfolio_sync_job)


async def schedule_prediction_evaluation(stop_event: asyncio.Event) -> None:
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
            await enqueue_task(prediction_tasks.prediction_evaluation_job)


async def schedule_news_poll(stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_news_poll_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing news source polling task.")
            await enqueue_task(news_tasks.poll_enabled_news_sources_job)


async def schedule_market_source_capability_refresh(stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    if settings.market_source_capability_refresh_on_startup:
        LOGGER.info("Queueing startup market source capability refresh task.")
        await enqueue_task(market_data_tasks.refresh_market_source_capability_map)

    interval = settings.market_source_capability_refresh_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing hourly market source capability refresh task.")
            await enqueue_task(market_data_tasks.refresh_market_source_capability_map)


async def schedule_hypothesis_evaluation(stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_hypothesis_eval_interval_seconds
    if interval <= 0 or not hypothesis_evaluation_surfaces_enabled(settings):
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing hypothesis evaluation task.")
            await enqueue_task(hypothesis_tasks.evaluate_hypotheses_job)


async def schedule_market_structure_snapshot_poll(stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_market_structure_snapshot_poll_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing market structure source polling task.")
            await enqueue_task(market_structure_tasks.poll_enabled_market_structure_sources_job)


async def schedule_market_structure_health_refresh(stop_event: asyncio.Event) -> None:
    await asyncio.sleep(1)
    if stop_event.is_set():
        return

    interval = settings.taskiq_market_structure_health_interval_seconds
    if interval <= 0:
        await stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            LOGGER.info("Queueing market structure source health refresh task.")
            await enqueue_task(market_structure_tasks.refresh_market_structure_source_health_job)


def start_scheduler(
    app: FastAPI,
    *,
    finish_event: asyncio.Event,
    backfill_event: asyncio.Event,
) -> Sequence[asyncio.Task[Any]]:
    tasks: list[asyncio.Task[Any]] = [
        asyncio.create_task(schedule_history_backfills(finish_event, backfill_event)),
        asyncio.create_task(enqueue_latest_price_snapshots(finish_event)),
        asyncio.create_task(schedule_pattern_statistics_refresh(finish_event)),
        asyncio.create_task(schedule_market_structure_refresh(finish_event)),
        asyncio.create_task(schedule_pattern_discovery_refresh(finish_event)),
        asyncio.create_task(schedule_strategy_discovery_refresh(finish_event)),
        asyncio.create_task(schedule_portfolio_sync(finish_event)),
        asyncio.create_task(schedule_prediction_evaluation(finish_event)),
        asyncio.create_task(schedule_news_poll(finish_event)),
        asyncio.create_task(schedule_market_source_capability_refresh(finish_event)),
    ]
    if hypothesis_evaluation_surfaces_enabled(settings):
        hypothesis_task = asyncio.create_task(schedule_hypothesis_evaluation(finish_event))
        tasks.append(hypothesis_task)
        app.state.taskiq_hypothesis_evaluation_task = hypothesis_task
    else:
        app.state.taskiq_hypothesis_evaluation_task = None
    market_structure_snapshot_task = asyncio.create_task(schedule_market_structure_snapshot_poll(finish_event))
    market_structure_health_task = asyncio.create_task(schedule_market_structure_health_refresh(finish_event))
    tasks.extend((market_structure_snapshot_task, market_structure_health_task))
    (
        app.state.taskiq_backfill_task,
        app.state.taskiq_refresh_task,
        app.state.taskiq_pattern_stats_task,
        app.state.taskiq_market_structure_task,
        app.state.taskiq_pattern_discovery_task,
        app.state.taskiq_strategy_discovery_task,
        app.state.taskiq_portfolio_sync_task,
        app.state.taskiq_prediction_evaluation_task,
        app.state.taskiq_news_poll_task,
        app.state.taskiq_market_source_capability_refresh_task,
        *remaining,
    ) = tasks
    if hypothesis_evaluation_surfaces_enabled(settings):
        (
            _hypothesis_task,
            app.state.taskiq_market_structure_snapshot_poll_task,
            app.state.taskiq_market_structure_health_task,
        ) = remaining
    else:
        (
            app.state.taskiq_market_structure_snapshot_poll_task,
            app.state.taskiq_market_structure_health_task,
        ) = remaining
    return tuple(tasks)
