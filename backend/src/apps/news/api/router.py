from fastapi import APIRouter

from src.apps.news.api import command_endpoints, job_endpoints, onboarding_endpoints, read_endpoints
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode
    router = APIRouter(prefix="/news")
    router.include_router(read_endpoints.router)
    if profile is not DeploymentProfile.HA_EMBEDDED:
        router.include_router(command_endpoints.router)
        router.include_router(job_endpoints.router)
        router.include_router(onboarding_endpoints.router)
    return router
