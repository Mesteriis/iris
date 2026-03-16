from fastapi import APIRouter, Request

from iris.apps.system.api.contracts import HealthRead, SystemStatusRead
from iris.apps.system.api.deps import SystemStatusFacadeDep
from iris.apps.system.api.presenters import health_read, system_status_read

router = APIRouter(tags=["system:read"])


@router.get("/status", response_model=SystemStatusRead, summary="Read system status")
async def status(request: Request, facade: SystemStatusFacadeDep) -> SystemStatusRead:
    worker_processes = getattr(request.app.state, "taskiq_worker_processes", [])
    return system_status_read(await facade.get_status(worker_processes=list(worker_processes)))


@router.get("/health", response_model=HealthRead, summary="Read system health")
async def health(facade: SystemStatusFacadeDep) -> HealthRead:
    await facade.ping()
    return health_read(status="healthy")
