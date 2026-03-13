from __future__ import annotations

from fastapi import APIRouter

from src.apps.control_plane.api.router import build_router as build_control_plane_router
from src.apps.hypothesis_engine.api.router import build_router as build_hypothesis_router
from src.apps.indicators.api.router import build_router as build_indicators_router
from src.apps.market_data.api.router import build_router as build_market_data_router
from src.apps.market_structure.api.router import build_router as build_market_structure_router
from src.apps.news.api.router import build_router as build_news_router
from src.apps.patterns.api.router import build_router as build_patterns_router
from src.apps.portfolio.api.router import build_router as build_portfolio_router
from src.apps.predictions.api.router import build_router as build_predictions_router
from src.apps.signals.api.router import build_router as build_signals_router
from src.apps.system.api.router import build_router as build_system_router
from src.core.http.launch_modes import DeploymentProfile, LaunchMode
from src.core.http.router_policy import normalize_path_prefix
from src.core.settings import Settings


def build_router(*, settings: Settings, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    router = APIRouter(prefix=normalize_path_prefix(settings.api_version_prefix))
    router.include_router(build_system_router(mode=mode, profile=profile))
    router.include_router(build_control_plane_router(mode=mode, profile=profile))
    router.include_router(build_market_data_router(mode=mode, profile=profile))
    router.include_router(build_market_structure_router(mode=mode, profile=profile))
    router.include_router(build_news_router(mode=mode, profile=profile))
    router.include_router(build_indicators_router(mode=mode, profile=profile))
    router.include_router(build_patterns_router(mode=mode, profile=profile))
    router.include_router(build_signals_router(mode=mode, profile=profile))
    router.include_router(build_portfolio_router(mode=mode, profile=profile))
    router.include_router(build_predictions_router(mode=mode, profile=profile))
    if settings.enable_hypothesis_engine:
        router.include_router(build_hypothesis_router(mode=mode, profile=profile))
    return router
