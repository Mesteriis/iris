from fastapi import APIRouter, Request

from iris.apps.frontend.api.contracts import FrontendDashboardSnapshotRead, FrontendShellSnapshotRead
from iris.apps.frontend.api.deps import FrontendReadDep
from iris.apps.frontend.api.presenters import frontend_dashboard_snapshot_read, frontend_shell_snapshot_read

router = APIRouter(tags=["frontend:read"])


@router.get("/shell", response_model=FrontendShellSnapshotRead, summary="Read frontend shell snapshot")
async def read_shell_snapshot(request: Request, facade: FrontendReadDep) -> FrontendShellSnapshotRead:
    worker_processes = getattr(request.app.state, "taskiq_worker_processes", [])
    return frontend_shell_snapshot_read(await facade.get_shell_snapshot(worker_processes=list(worker_processes)))


@router.get("/dashboard", response_model=FrontendDashboardSnapshotRead, summary="Read frontend dashboard snapshot")
async def read_dashboard_snapshot(request: Request, facade: FrontendReadDep) -> FrontendDashboardSnapshotRead:
    worker_processes = getattr(request.app.state, "taskiq_worker_processes", [])
    return frontend_dashboard_snapshot_read(await facade.get_dashboard_snapshot(worker_processes=list(worker_processes)))
