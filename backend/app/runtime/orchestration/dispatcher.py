from __future__ import annotations

from typing import Any

async def enqueue_task(task: object, *args: Any, **kwargs: Any) -> None:
    await task.kiq(*args, **kwargs)  # type: ignore[attr-defined]


async def dispatch_task_locally(receiver: object, task: object, *args: Any, **kwargs: Any) -> None:
    del receiver
    await enqueue_task(task, *args, **kwargs)
