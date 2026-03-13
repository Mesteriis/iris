from __future__ import annotations

from fastapi import APIRouter

from src.apps.hypothesis_engine.api import command_endpoints, job_endpoints, read_endpoints, stream_endpoints
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode
    router = APIRouter(prefix="/hypothesis")
    router.include_router(read_endpoints.router)
    router.include_router(command_endpoints.router)
    if profile is not DeploymentProfile.HA_EMBEDDED:
        router.include_router(job_endpoints.router)
        router.include_router(stream_endpoints.router)
    return router
