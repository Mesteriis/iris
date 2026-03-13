from __future__ import annotations

from fastapi import APIRouter

from src.apps.control_plane.api import command_endpoints, read_endpoints
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode
    router = APIRouter(prefix="/control-plane", tags=["control-plane"])
    router.include_router(read_endpoints.router)
    if profile is not DeploymentProfile.HA_EMBEDDED:
        router.include_router(command_endpoints.router)
    return router
