from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from src.apps.integrations.ha.application.services import HABridgeService
from src.apps.integrations.ha.bridge.runtime import HABridgeRuntime
from src.apps.integrations.ha.bridge.websocket_hub import HAWebSocketHub


def get_ha_bridge_runtime(connection: HTTPConnection) -> HABridgeRuntime:
    runtime = getattr(connection.app.state, "ha_bridge_runtime", None)
    if runtime is None:
        service = getattr(connection.app.state, "ha_bridge_service", None)
        if service is None:
            service = HABridgeService()
            connection.app.state.ha_bridge_service = service
        runtime = HABridgeRuntime(service=service)
        connection.app.state.ha_bridge_runtime = runtime
    return runtime


_HA_BRIDGE_RUNTIME_DEP = Depends(get_ha_bridge_runtime)


def get_ha_bridge_service(runtime: HABridgeRuntime = _HA_BRIDGE_RUNTIME_DEP) -> HABridgeService:
    return runtime.service


async def get_started_ha_bridge_runtime(
    runtime: HABridgeRuntime = _HA_BRIDGE_RUNTIME_DEP,
) -> HABridgeRuntime:
    await runtime.ensure_started()
    return runtime


def get_ha_websocket_hub(runtime: HABridgeRuntime = _HA_BRIDGE_RUNTIME_DEP) -> HAWebSocketHub:
    return runtime.hub


HABridgeServiceDep = Annotated[HABridgeService, Depends(get_ha_bridge_service)]
HABridgeRuntimeDep = Annotated[HABridgeRuntime, Depends(get_ha_bridge_runtime)]
StartedHABridgeRuntimeDep = Annotated[HABridgeRuntime, Depends(get_started_ha_bridge_runtime)]
HAWebSocketHubDep = Annotated[HAWebSocketHub, Depends(get_ha_websocket_hub)]


__all__ = [
    "HABridgeRuntimeDep",
    "HABridgeServiceDep",
    "HAWebSocketHubDep",
    "StartedHABridgeRuntimeDep",
    "get_ha_bridge_runtime",
    "get_ha_bridge_service",
    "get_ha_websocket_hub",
    "get_started_ha_bridge_runtime",
]
