from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException, status
from pydantic import ValidationError

from src.apps.integrations.ha.api.deps import HABridgeServiceDep, HAWebSocketHubDep, StartedHABridgeRuntimeDep
from src.apps.integrations.ha.errors import HACommandDispatchError
from src.apps.integrations.ha.schemas import (
    HACommandExecuteMessage,
    HAHelloMessage,
    HAPingMessage,
    HASubscribeMessage,
    HAUnsubscribeMessage,
)

router = APIRouter(tags=["ha:websocket"])


@router.websocket("/ws")
async def websocket_bridge(
    websocket: WebSocket,
    runtime: StartedHABridgeRuntimeDep,
    service: HABridgeServiceDep,
    hub: HAWebSocketHubDep,
) -> None:
    await websocket.accept()
    session = None
    sender_task = None
    try:
        hello_raw = await websocket.receive_json()
        hello = HAHelloMessage.model_validate(hello_raw)
        if hello.protocol_version != service.instance().protocol_version:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="unsupported_protocol_version",
            )
        await hub.send_welcome(websocket, hello)
        session = await hub.register_session()
        sender_task = asyncio.create_task(_forward_session_messages(websocket, hub, session.session_id))

        while True:
            payload = await websocket.receive_json()
            message_type = str(payload.get("type") or "")
            if message_type == "subscribe":
                message = HASubscribeMessage.model_validate(payload)
                preview = _merge_subscription(session.subscription, message)
                await hub.send_initial_sync(websocket, preview)
                session = await hub.update_subscription(session.session_id, message, primed=True)
                continue
            if message_type == "unsubscribe":
                message = HAUnsubscribeMessage.model_validate(payload)
                session = await hub.remove_subscription(
                    session.session_id,
                    HASubscribeMessage(
                        type="subscribe",
                        entities=message.entities,
                        collections=message.collections,
                        operations=message.operations,
                        catalog=message.catalog,
                        dashboard=message.dashboard,
                    )
                )
                continue
            if message_type == "ping":
                message = HAPingMessage.model_validate(payload)
                await websocket.send_json({"type": "pong", "timestamp": message.timestamp})
                continue
            if message_type == "command_execute":
                message = HACommandExecuteMessage.model_validate(payload)
                try:
                    dispatch = await service.execute_command(command=message.command, payload=message.payload)
                except HACommandDispatchError as exc:
                    await websocket.send_json(
                        service.command_error_ack(
                            request_id=message.request_id,
                            code=exc.code,
                            message=exc.message,
                            details=exc.details,
                            retryable=exc.retryable,
                        )
                    )
                    continue
                await websocket.send_json(
                    service.command_accepted_ack(
                        request_id=message.request_id,
                        operation_id=dispatch.operation_id,
                    )
                )
                if dispatch.outbound_messages:
                    await hub.broadcast_messages(dispatch.outbound_messages)
                await runtime.track_operation(
                    operation_id=dispatch.operation_id,
                    command=dispatch.command,
                )
                continue
            if message_type == "ack_event":
                continue
            raise WebSocketException(
                code=status.WS_1003_UNSUPPORTED_DATA,
                reason="invalid_message",
            )
    except ValidationError as exc:
        raise WebSocketException(code=status.WS_1003_UNSUPPORTED_DATA, reason=str(exc)) from exc
    except WebSocketDisconnect:
        return
    finally:
        if sender_task is not None:
            sender_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender_task
        if session is not None:
            await hub.unregister_session(session.session_id)


async def _forward_session_messages(websocket: WebSocket, hub: HAWebSocketHubDep, session_id: str) -> None:
    while True:
        queued = await hub.next_message(session_id)
        await websocket.send_json(queued.payload)
        if queued.close:
            await websocket.close(
                code=queued.close_code or status.WS_1013_TRY_AGAIN_LATER,
                reason=queued.close_reason,
            )
            return


def _merge_subscription(current, payload: HASubscribeMessage):
    merged = type(current)(
        entities=set(current.entities),
        collections=set(current.collections),
        operations=current.operations,
        catalog=current.catalog,
        dashboard=current.dashboard,
    )
    merged.update(payload)
    return merged
