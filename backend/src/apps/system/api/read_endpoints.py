from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.apps.system.api.contracts import HealthRead, SystemStatusRead
from src.apps.system.api.deps import SystemStatusFacade, get_system_status_facade
from src.apps.system.api.presenters import health_read, system_status_read

router = APIRouter(tags=["system:read"])
SystemStatusDep = Annotated[SystemStatusFacade, Depends(get_system_status_facade)]


@router.get("/status", response_model=SystemStatusRead, summary="Read system status")
async def status(request: Request, facade: SystemStatusDep) -> SystemStatusRead:
    worker_processes = getattr(request.app.state, "taskiq_worker_processes", [])
    return system_status_read(await facade.get_status(worker_processes=list(worker_processes)))


@router.get("/health", response_model=HealthRead, summary="Read system health")
async def health(facade: SystemStatusDep) -> HealthRead:
    await facade.ping()
    return health_read(status="healthy")
