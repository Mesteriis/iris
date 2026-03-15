from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, status

from src.apps.integrations.ha.application.services import HABridgeService
from src.apps.integrations.ha.schemas import HAHelloMessage, HASubscribeMessage, HAWelcomeMessage
from src.core.settings import get_settings


@dataclass(slots=True)
class HASubscriptionState:
    entities: set[str] = field(default_factory=set)
    collections: set[str] = field(default_factory=set)
    operations: bool = False
    catalog: bool = False
    dashboard: bool = False

    def update(self, payload: HASubscribeMessage) -> None:
        self.entities.update(payload.entities)
        self.collections.update(payload.collections)
        self.operations = self.operations or payload.operations
        self.catalog = self.catalog or payload.catalog
        self.dashboard = self.dashboard or payload.dashboard

    def remove(self, payload: HASubscribeMessage) -> None:
        self.entities.difference_update(payload.entities)
        self.collections.difference_update(payload.collections)
        if payload.operations:
            self.operations = False
        if payload.catalog:
            self.catalog = False
        if payload.dashboard:
            self.dashboard = False


@dataclass(slots=True)
class HASession:
    session_id: str
    queue: deque[HAQueuedMessage] = field(default_factory=deque)
    queue_ready: asyncio.Event = field(default_factory=asyncio.Event)
    subscription: HASubscriptionState = field(default_factory=HASubscriptionState)
    primed: bool = False
    closing: bool = False


@dataclass(slots=True, frozen=True)
class HAQueuedMessage:
    payload: dict[str, Any]
    close: bool = False
    close_code: int | None = None
    close_reason: str | None = None


class HAWebSocketHub:
    def __init__(self, service: HABridgeService, *, max_queue_depth: int | None = None) -> None:
        self._service = service
        self._sessions: dict[str, HASession] = {}
        self._lock = asyncio.Lock()
        self._max_queue_depth = max_queue_depth or get_settings().ha_websocket_session_queue_depth

    async def register_session(self) -> HASession:
        session = HASession(session_id=uuid4().hex)
        async with self._lock:
            self._sessions[session.session_id] = session
        return session

    async def unregister_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def update_subscription(self, session_id: str, payload: HASubscribeMessage, *, primed: bool = True) -> HASession:
        async with self._lock:
            session = self._sessions[session_id]
            session.subscription.update(payload)
            session.primed = primed
            return session

    async def remove_subscription(self, session_id: str, payload: HASubscribeMessage) -> HASession:
        async with self._lock:
            session = self._sessions[session_id]
            session.subscription.remove(payload)
            return session

    async def next_message(self, session_id: str) -> HAQueuedMessage:
        while True:
            async with self._lock:
                session = self._sessions[session_id]
                if session.queue:
                    message = session.queue.popleft()
                    if not session.queue:
                        session.queue_ready.clear()
                    return message
                ready = session.queue_ready
            await ready.wait()

    async def broadcast_messages(self, messages: Iterable[dict[str, Any]]) -> None:
        async with self._lock:
            sessions = tuple(self._sessions.values())
            for message in messages:
                for session in sessions:
                    if self._wants_message(session, message):
                        self._enqueue_message_locked(session, message)

    async def send_welcome(self, websocket: WebSocket, hello: HAHelloMessage) -> None:
        del hello
        await websocket.send_json(
            HAWelcomeMessage(
                protocol_version=self._service.instance().protocol_version,
                instance=self._service.instance(),
                capabilities=self._service.capabilities(),
            ).model_dump(mode="json")
        )

    async def send_initial_sync(self, websocket: WebSocket, subscription: HASubscriptionState) -> None:
        if subscription.entities:
            for message in await self._service.entity_state_messages(sorted(subscription.entities)):
                await websocket.send_json(message)
        if subscription.collections:
            for message in await self._service.collection_snapshot_messages(sorted(subscription.collections)):
                await websocket.send_json(message)
        await websocket.send_json(self._service.system_health_message())

    @staticmethod
    def _wants_message(session: HASession, message: dict[str, Any]) -> bool:
        message_type = str(message.get("type") or "")
        subscription = session.subscription
        has_subscription = bool(
            subscription.entities
            or subscription.collections
            or subscription.operations
            or subscription.catalog
            or subscription.dashboard
        )
        if message_type in {"pong", "command_ack"}:
            return True
        if not session.primed or not has_subscription:
            return False
        if message_type in {"event_emitted", "system_health"}:
            return True
        if message_type == "entity_state_changed":
            entity_key = str(message.get("entity_key") or "")
            return "*" in subscription.entities or entity_key in subscription.entities
        if message_type in {"collection_snapshot", "collection_patch"}:
            collection_key = str(message.get("collection_key") or "")
            return collection_key in subscription.collections
        if message_type == "operation_update":
            return subscription.operations
        if message_type == "catalog_changed":
            return subscription.catalog
        if message_type == "dashboard_changed":
            return subscription.dashboard
        if message_type == "state_patch":
            return bool(subscription.entities or subscription.collections or subscription.operations)
        return False

    def _enqueue_message_locked(self, session: HASession, message: dict[str, Any]) -> None:
        if session.closing:
            return
        if len(session.queue) >= self._max_queue_depth:
            self._mark_resync_required_locked(session, reason="queue_overflow")
            return
        session.queue.append(HAQueuedMessage(payload=message))
        session.queue_ready.set()

    def _mark_resync_required_locked(self, session: HASession, *, reason: str) -> None:
        if session.closing:
            return
        session.queue.clear()
        session.queue.append(
            HAQueuedMessage(
                payload=self._service.resync_required_message(
                    reason=reason,
                    message="Outbound session queue overflowed. Client must perform a full state resync.",
                ),
                close=True,
                close_code=status.WS_1013_TRY_AGAIN_LATER,
                close_reason="resync_required",
            )
        )
        session.queue_ready.set()
        session.closing = True
