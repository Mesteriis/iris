from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass

from src.apps.integrations.ha.application.services import HABridgeService
from src.apps.integrations.ha.bridge.event_consumer import create_ha_bridge_consumer, ensure_ha_bridge_group
from src.apps.integrations.ha.bridge.websocket_hub import HAWebSocketHub
from src.runtime.streams.consumer import EventConsumer
from src.runtime.streams.types import IrisEvent


@dataclass(slots=True)
class HATrackedOperation:
    operation_id: str
    command: str
    last_signature: str | None = None


class HABridgeRuntime:
    def __init__(
        self,
        *,
        service: HABridgeService | None = None,
        websocket_queue_depth: int | None = None,
    ) -> None:
        self.service = service or HABridgeService()
        self.hub = HAWebSocketHub(self.service, max_queue_depth=websocket_queue_depth)
        self._consumer: EventConsumer | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._operation_task: asyncio.Task[None] | None = None
        self._started = False
        self._start_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._tracked_operations: dict[str, HATrackedOperation] = {}
        self._tracked_operations_lock = asyncio.Lock()

    async def ensure_started(self) -> None:
        async with self._start_lock:
            if self._started:
                return
            self._stop_event = asyncio.Event()
            await ensure_ha_bridge_group()
            self._consumer = create_ha_bridge_consumer(handler=self.handle_event)
            self._event_task = asyncio.create_task(
                self._consumer.run_async(stop_checker=self._stop_event.is_set),
                name="iris-ha-bridge-runtime",
            )
            self._operation_task = asyncio.create_task(
                self._poll_operations_loop(),
                name="iris-ha-bridge-operations",
            )
            self._started = True

    async def stop(self) -> None:
        async with self._start_lock:
            if not self._started:
                return
            self._stop_event.set()
            if self._consumer is not None:
                self._consumer.stop()
            if self._event_task is not None:
                self._event_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._event_task
            if self._operation_task is not None:
                self._operation_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._operation_task
            if self._consumer is not None:
                await self._consumer.close_async()
            self._consumer = None
            self._event_task = None
            self._operation_task = None
            self._started = False
            async with self._tracked_operations_lock:
                self._tracked_operations.clear()

    async def handle_event(self, event: IrisEvent) -> None:
        messages = await self.service.apply_event(event)
        await self.hub.broadcast_messages(messages)

    async def track_operation(self, *, operation_id: str, command: str) -> None:
        async with self._tracked_operations_lock:
            tracked = self._tracked_operations.get(operation_id)
            if tracked is None:
                tracked = HATrackedOperation(operation_id=operation_id, command=command)
                self._tracked_operations[operation_id] = tracked
            else:
                tracked.command = command
        await self._emit_tracked_operation_update(operation_id)

    async def _poll_operations_loop(self) -> None:
        while not self._stop_event.is_set():
            await self._poll_tracked_operations_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=1.0)
            except TimeoutError:
                continue

    async def _poll_tracked_operations_once(self) -> None:
        async with self._tracked_operations_lock:
            tracked_operations = tuple(self._tracked_operations.values())
        for tracked in tracked_operations:
            await self._emit_tracked_operation_update(tracked.operation_id)

    async def _emit_tracked_operation_update(self, operation_id: str) -> None:
        async with self._tracked_operations_lock:
            tracked = self._tracked_operations.get(operation_id)
        if tracked is None:
            return
        message = await self.service.operation_update_message(
            operation_id=tracked.operation_id,
            command=tracked.command,
        )
        if message is None:
            async with self._tracked_operations_lock:
                self._tracked_operations.pop(operation_id, None)
            return
        signature_payload = {
            key: value
            for key, value in message.items()
            if key not in {"projection_epoch", "sequence"}
        }
        signature = json.dumps(signature_payload, sort_keys=True, separators=(",", ":"))
        if tracked.last_signature == signature:
            return
        tracked.last_signature = signature
        await self.hub.broadcast_messages([message])
        if str(message.get("status") or "") in {"completed", "failed", "cancelled"}:
            async with self._tracked_operations_lock:
                self._tracked_operations.pop(operation_id, None)


__all__ = ["HABridgeRuntime"]
