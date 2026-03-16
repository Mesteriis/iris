from fastapi import APIRouter

from iris.apps.market_data.api import command_endpoints, job_endpoints, read_endpoints
from iris.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode
    del profile
    router = APIRouter()
    router.include_router(read_endpoints.router)
    router.include_router(command_endpoints.router)
    router.include_router(job_endpoints.router)
    return router
