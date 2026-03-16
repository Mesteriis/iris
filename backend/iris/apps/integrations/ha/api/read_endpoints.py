from fastapi import APIRouter
from fastapi.responses import JSONResponse

from iris.apps.integrations.ha.api.contracts import (
    HABootstrapRead,
    HACatalogRead,
    HADashboardRead,
    HAHealthRead,
    HAOperationRead,
    HAStateSnapshotRead,
)
from iris.apps.integrations.ha.api.deps import HABridgeFacadeDep

router = APIRouter(tags=["ha:read"])


@router.get("/health", response_model=HAHealthRead, summary="Read Home Assistant bridge health")
async def read_health(facade: HABridgeFacadeDep) -> HAHealthRead:
    return facade.health()


@router.get("/bootstrap", response_model=HABootstrapRead, summary="Read Home Assistant bridge bootstrap metadata")
async def read_bootstrap(facade: HABridgeFacadeDep) -> HABootstrapRead:
    return facade.bootstrap()


@router.get("/catalog", response_model=HACatalogRead, summary="Read Home Assistant bridge catalog")
async def read_catalog(facade: HABridgeFacadeDep) -> HACatalogRead:
    return facade.catalog()


@router.get("/dashboard", response_model=HADashboardRead, summary="Read Home Assistant dashboard schema")
async def read_dashboard(facade: HABridgeFacadeDep) -> HADashboardRead:
    return facade.dashboard()


@router.get("/state", response_model=HAStateSnapshotRead, summary="Read Home Assistant runtime state snapshot")
async def read_state(facade: HABridgeFacadeDep) -> HAStateSnapshotRead:
    return await facade.state_snapshot()


@router.get("/operations/{operation_id}", response_model=HAOperationRead, summary="Read Home Assistant operation snapshot")
async def read_operation(operation_id: str, facade: HABridgeFacadeDep) -> HAOperationRead | JSONResponse:
    payload = await facade.operation_status(operation_id)
    if payload is not None:
        return payload
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "operation_not_found",
                "message": "Operation was not found.",
                "details": {"operation_id": operation_id},
            }
        },
    )
