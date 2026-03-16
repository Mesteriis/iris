from fastapi import APIRouter

from iris.apps.explanations.api import job_endpoints, read_endpoints
from iris.core.ai import explain_generation_runtime_enabled
from iris.core.http.launch_modes import DeploymentProfile, LaunchMode
from iris.core.settings import Settings, get_settings


def build_router(*, mode: LaunchMode, profile: DeploymentProfile, settings: Settings | None = None) -> APIRouter:
    del mode
    effective_settings = settings or get_settings()
    router = APIRouter(prefix="/explanations")
    router.include_router(read_endpoints.router)
    if profile is not DeploymentProfile.HA_EMBEDDED and explain_generation_runtime_enabled(effective_settings):
        router.include_router(job_endpoints.router)
    return router


__all__ = ["build_router"]
