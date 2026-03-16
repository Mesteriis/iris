from fastapi import APIRouter

from src.api.v1.router import build_router as build_v1_router
from src.core.http.launch_modes import resolve_deployment_profile, resolve_launch_mode
from src.core.http.router_policy import normalize_path_prefix
from src.core.settings import Settings


def build_router(settings: Settings) -> APIRouter:
    mode = resolve_launch_mode(settings.api_launch_mode)
    profile = resolve_deployment_profile(settings.api_deployment_profile, mode=mode)
    router = APIRouter(prefix=normalize_path_prefix(settings.api_root_prefix))
    router.include_router(build_v1_router(settings=settings, mode=mode, profile=profile))
    return router
