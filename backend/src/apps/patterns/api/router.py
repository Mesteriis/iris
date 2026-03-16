from fastapi import APIRouter

from src.apps.patterns.api import command_endpoints, read_endpoints
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode, profile
    router = APIRouter()
    router.include_router(read_endpoints.router)
    router.include_router(command_endpoints.router)
    return router
