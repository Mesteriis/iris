from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from iris.apps.integrations.ha.application.services import HABridgeFacade
from iris.apps.integrations.ha.bridge.runtime import HABridgeRuntime
from iris.apps.integrations.ha.bridge.websocket_hub import HAWebSocketHub


def get_ha_bridge_runtime(connection: HTTPConnection) -> HABridgeRuntime:
    runtime = getattr(connection.app.state, "ha_bridge_runtime", None)
    if runtime is None:
        facade = getattr(connection.app.state, "ha_bridge_facade", None)
        if facade is None:
            facade = HABridgeFacade()
            connection.app.state.ha_bridge_facade = facade
        runtime = HABridgeRuntime(facade=facade)
        connection.app.state.ha_bridge_runtime = runtime
    return runtime


_HA_BRIDGE_RUNTIME_DEP = Depends(get_ha_bridge_runtime)


def get_ha_bridge_facade(runtime: HABridgeRuntime = _HA_BRIDGE_RUNTIME_DEP) -> HABridgeFacade:
    return runtime.facade


async def get_started_ha_bridge_runtime(
    runtime: HABridgeRuntime = _HA_BRIDGE_RUNTIME_DEP,
) -> HABridgeRuntime:
    await runtime.ensure_started()
    return runtime


def get_ha_websocket_hub(runtime: HABridgeRuntime = _HA_BRIDGE_RUNTIME_DEP) -> HAWebSocketHub:
    return runtime.hub


HABridgeFacadeDep = Annotated[HABridgeFacade, Depends(get_ha_bridge_facade)]
HABridgeRuntimeDep = Annotated[HABridgeRuntime, Depends(get_ha_bridge_runtime)]
StartedHABridgeRuntimeDep = Annotated[HABridgeRuntime, Depends(get_started_ha_bridge_runtime)]
HAWebSocketHubDep = Annotated[HAWebSocketHub, Depends(get_ha_websocket_hub)]


__all__ = [
    "HABridgeFacadeDep",
    "HABridgeRuntimeDep",
    "HAWebSocketHubDep",
    "StartedHABridgeRuntimeDep",
    "get_ha_bridge_facade",
    "get_ha_bridge_runtime",
    "get_ha_websocket_hub",
    "get_started_ha_bridge_runtime",
]
