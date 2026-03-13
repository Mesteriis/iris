from __future__ import annotations

from fastapi import APIRouter

from src.apps.system.api import read_endpoints
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode, profile
    router = APIRouter(prefix="/system")
    router.include_router(read_endpoints.router)
    return router
