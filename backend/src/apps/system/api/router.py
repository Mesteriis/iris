from fastapi import APIRouter

from src.apps.system.api import operation_endpoints, read_endpoints
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode, profile
    router = APIRouter()
    router.include_router(operation_endpoints.router)

    system_router = APIRouter(prefix="/system")
    system_router.include_router(read_endpoints.router)
    router.include_router(system_router)
    return router
