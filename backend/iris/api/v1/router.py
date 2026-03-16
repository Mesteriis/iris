from fastapi import APIRouter

from iris.apps.briefs.api.router import build_router as build_briefs_router
from iris.apps.control_plane.api.router import build_router as build_control_plane_router
from iris.apps.explanations.api.router import build_router as build_explanations_router
from iris.apps.frontend.api.router import build_router as build_frontend_router
from iris.apps.hypothesis_engine.api.router import build_router as build_hypothesis_router
from iris.apps.indicators.api.router import build_router as build_indicators_router
from iris.apps.integrations.ha.api.router import build_router as build_ha_router
from iris.apps.market_data.api.router import build_router as build_market_data_router
from iris.apps.market_structure.api.router import build_router as build_market_structure_router
from iris.apps.news.api.router import build_router as build_news_router
from iris.apps.notifications.api.router import build_router as build_notifications_router
from iris.apps.patterns.api.router import build_router as build_patterns_router
from iris.apps.portfolio.api.router import build_router as build_portfolio_router
from iris.apps.predictions.api.router import build_router as build_predictions_router
from iris.apps.signals.api.router import build_router as build_signals_router
from iris.apps.system.api.router import build_router as build_system_router
from iris.core.http.launch_modes import DeploymentProfile, LaunchMode
from iris.core.http.router_policy import normalize_path_prefix
from iris.core.settings import Settings


def build_router(*, settings: Settings, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    router = APIRouter(prefix=normalize_path_prefix(settings.api_version_prefix))
    router.include_router(build_system_router(mode=mode, profile=profile))
    router.include_router(build_ha_router(mode=mode, profile=profile))
    router.include_router(build_control_plane_router(mode=mode, profile=profile))
    router.include_router(build_briefs_router(mode=mode, profile=profile, settings=settings))
    router.include_router(build_explanations_router(mode=mode, profile=profile, settings=settings))
    router.include_router(build_frontend_router(mode=mode, profile=profile))
    router.include_router(build_market_data_router(mode=mode, profile=profile))
    router.include_router(build_market_structure_router(mode=mode, profile=profile))
    router.include_router(build_news_router(mode=mode, profile=profile))
    router.include_router(build_notifications_router(mode=mode, profile=profile))
    router.include_router(build_indicators_router(mode=mode, profile=profile))
    router.include_router(build_patterns_router(mode=mode, profile=profile))
    router.include_router(build_signals_router(mode=mode, profile=profile))
    router.include_router(build_portfolio_router(mode=mode, profile=profile))
    router.include_router(build_predictions_router(mode=mode, profile=profile))
    router.include_router(build_hypothesis_router(mode=mode, profile=profile, settings=settings))
    return router
