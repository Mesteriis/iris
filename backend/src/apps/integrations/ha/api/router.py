from __future__ import annotations

from fastapi import APIRouter

from src.apps.integrations.ha.api import read_endpoints, websocket_endpoints
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode, profile
    router = APIRouter(prefix="/ha")
    router.include_router(read_endpoints.router)
    router.include_router(websocket_endpoints.router)
    return router
