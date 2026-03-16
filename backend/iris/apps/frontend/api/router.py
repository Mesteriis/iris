from fastapi import APIRouter

from iris.apps.frontend.api import read_endpoints, stream_endpoints
from iris.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode
    del profile
    router = APIRouter(prefix="/frontend")
    router.include_router(read_endpoints.router)
    router.include_router(stream_endpoints.router)
    return router
