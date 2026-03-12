from __future__ import annotations

import asyncio
import multiprocessing
import signal
from dataclasses import dataclass

from taskiq.receiver import Receiver

from app.core.settings import get_settings

settings = get_settings()


@dataclass(frozen=True)
class TaskiqWorkerGroup:
    name: str
    process_count: int


TASKIQ_WORKER_GROUPS = (
    TaskiqWorkerGroup(name="taskiq-general", process_count=max(settings.taskiq_general_worker_processes, 0)),
    TaskiqWorkerGroup(name="taskiq-analytics", process_count=max(settings.taskiq_analytics_worker_processes, 0)),
)


def _load_worker_broker(group_name: str):
    if group_name == "taskiq-general":
        from app.apps.market_structure import tasks as market_structure_tasks
        from app.apps.market_data import tasks as market_data_tasks
        from app.apps.news import tasks as news_tasks
        from app.apps.portfolio import tasks as portfolio_tasks
        from app.runtime.orchestration.broker import broker

        del market_data_tasks, market_structure_tasks, news_tasks, portfolio_tasks
        return broker

    if group_name == "taskiq-analytics":
        from app.apps.anomalies import tasks as anomaly_tasks
        from app.apps.patterns import tasks as pattern_tasks
        from app.apps.predictions import tasks as prediction_tasks
        from app.runtime.orchestration.broker import analytics_broker

        del anomaly_tasks, pattern_tasks, prediction_tasks
        return analytics_broker

    raise ValueError(f"Unsupported TaskIQ worker group '{group_name}'.")


async def _watch_stop_flag(stop_flag, finish_event: asyncio.Event) -> None:
    while not stop_flag.is_set():
        await asyncio.sleep(0.25)
    finish_event.set()


async def _serve_taskiq_worker(group_name: str, stop_flag) -> None:
    broker = _load_worker_broker(group_name)
    finish_event = asyncio.Event()
    await broker.startup()
    receiver = Receiver(broker=broker, run_startup=False)
    listener_task = asyncio.create_task(receiver.listen(finish_event))
    watcher_task = asyncio.create_task(_watch_stop_flag(stop_flag, finish_event))
    try:
        done, _ = await asyncio.wait(
            {listener_task, watcher_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        finish_event.set()
        if listener_task in done:
            listener_task.result()
        else:
            await listener_task
    finally:
        finish_event.set()
        watcher_task.cancel()
        await asyncio.gather(watcher_task, return_exceptions=True)
        await broker.shutdown()


def _run_group_with_stop(group_name: str, stop_flag) -> None:
    def _stop_handler(signum, frame):  # pragma: no cover
        del signum, frame
        stop_flag.set()

    signal.signal(signal.SIGTERM, _stop_handler)
    signal.signal(signal.SIGINT, _stop_handler)
    asyncio.run(_serve_taskiq_worker(group_name, stop_flag))


def spawn_taskiq_worker_processes() -> tuple[multiprocessing.synchronize.Event, list[multiprocessing.Process]]:
    ctx = multiprocessing.get_context("spawn")
    stop_event = ctx.Event()
    processes: list[multiprocessing.Process] = []
    for group in TASKIQ_WORKER_GROUPS:
        for index in range(group.process_count):
            process = ctx.Process(
                target=_run_group_with_stop,
                args=(group.name, stop_event),
                daemon=True,
                name=f"iris-{group.name}-{index + 1}",
            )
            process.start()
            processes.append(process)
    return stop_event, processes


def stop_taskiq_worker_processes(
    stop_event,
    processes: list[multiprocessing.Process],
) -> None:
    stop_event.set()
    for process in processes:
        process.join(timeout=5.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)
