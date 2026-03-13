from __future__ import annotations

from fastapi import APIRouter

from src.apps.control_plane.api.router import build_router as build_control_plane_router
from src.apps.hypothesis_engine.views import router as hypothesis_router
from src.apps.indicators.views import router as indicators_router
from src.apps.market_data.views import router as market_data_router
from src.apps.market_structure.views import router as market_structure_router
from src.apps.news.views import router as news_router
from src.apps.patterns.views import router as patterns_router
from src.apps.portfolio.views import router as portfolio_router
from src.apps.predictions.views import router as predictions_router
from src.apps.signals.views import router as signals_router
from src.apps.system.views import router as system_router
from src.core.http.launch_modes import DeploymentProfile, LaunchMode
from src.core.http.router_policy import normalize_path_prefix
from src.core.settings import Settings


def build_router(*, settings: Settings, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    router = APIRouter(prefix=normalize_path_prefix(settings.api_version_prefix))
    router.include_router(system_router, prefix="/system")
    router.include_router(build_control_plane_router(mode=mode, profile=profile))
    router.include_router(market_data_router)
    router.include_router(market_structure_router)
    router.include_router(news_router)
    router.include_router(indicators_router)
    router.include_router(patterns_router)
    router.include_router(signals_router)
    router.include_router(portfolio_router)
    router.include_router(predictions_router)
    if settings.enable_hypothesis_engine:
        router.include_router(hypothesis_router)
    return router
