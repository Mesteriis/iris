from fastapi import APIRouter

from iris.apps.patterns.api import command_endpoints, read_endpoints
from iris.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode, profile
    router = APIRouter()
    router.include_router(read_endpoints.router)
    router.include_router(command_endpoints.router)
    return router
