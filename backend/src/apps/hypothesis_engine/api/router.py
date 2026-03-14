from __future__ import annotations

from fastapi import APIRouter

from src.apps.hypothesis_engine.api import job_endpoints, read_endpoints, stream_endpoints
from src.core.ai import hypothesis_evaluation_surfaces_enabled, hypothesis_stream_surfaces_enabled
from src.core.http.launch_modes import DeploymentProfile, LaunchMode
from src.core.settings import Settings, get_settings


def build_router(*, mode: LaunchMode, profile: DeploymentProfile, settings: Settings | None = None) -> APIRouter:
    del mode
    effective_settings = settings or get_settings()
    router = APIRouter(prefix="/hypothesis")
    router.include_router(read_endpoints.router)
    if hypothesis_evaluation_surfaces_enabled(effective_settings):
        router.include_router(job_endpoints.router)
    if hypothesis_stream_surfaces_enabled(settings=effective_settings, profile=profile):
        router.include_router(stream_endpoints.router)
    return router
