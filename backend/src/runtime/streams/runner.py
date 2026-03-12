from __future__ import annotations

import multiprocessing
import signal

from src.runtime.control_plane.worker import create_topology_dispatcher_consumer
from src.runtime.streams.workers import EVENT_WORKER_GROUPS, create_worker


def run_worker_loop(group_name: str) -> None:
    worker = create_worker(group_name)
    try:
        worker.run()
    finally:
        worker.close()


def _run_group_with_stop(group_name: str, stop_flag) -> None:
    worker = create_worker(group_name)

    def _stop_handler(signum, frame):  # pragma: no cover
        del signum, frame
        worker.stop()

    signal.signal(signal.SIGTERM, _stop_handler)
    signal.signal(signal.SIGINT, _stop_handler)
    try:
        worker.run(stop_checker=stop_flag.is_set)
    finally:
        worker.stop()
        worker.close()


def _run_topology_dispatcher_with_stop(stop_flag) -> None:
    worker = create_topology_dispatcher_consumer()

    def _stop_handler(signum, frame):  # pragma: no cover
        del signum, frame
        worker.stop()

    signal.signal(signal.SIGTERM, _stop_handler)
    signal.signal(signal.SIGINT, _stop_handler)
    try:
        worker.run(stop_checker=stop_flag.is_set)
    finally:
        worker.stop()
        worker.close()


def spawn_event_worker_processes() -> tuple[multiprocessing.synchronize.Event, list[multiprocessing.Process]]:
    ctx = multiprocessing.get_context("spawn")
    stop_event = ctx.Event()
    processes: list[multiprocessing.Process] = []
    dispatcher_process = ctx.Process(
        target=_run_topology_dispatcher_with_stop,
        args=(stop_event,),
        daemon=True,
        name="iris-control-plane-dispatcher",
    )
    dispatcher_process.start()
    processes.append(dispatcher_process)
    for group_name in EVENT_WORKER_GROUPS:
        process = ctx.Process(
            target=_run_group_with_stop,
            args=(group_name, stop_event),
            daemon=True,
            name=f"iris-{group_name}",
        )
        process.start()
        processes.append(process)
    return stop_event, processes


def stop_event_worker_processes(
    stop_event,
    processes: list[multiprocessing.Process],
) -> None:
    stop_event.set()
    for process in processes:
        process.join(timeout=5.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)
