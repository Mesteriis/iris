from __future__ import annotations

from fastapi import APIRouter

from src.apps.notifications.api import read_endpoints
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode, profile
    router = APIRouter()
    router.include_router(read_endpoints.router)
    return router


__all__ = ["build_router"]
