from __future__ import annotations

from fastapi import APIRouter

from src.apps.signals.api import (
    backtest_endpoints,
    decision_endpoints,
    final_signal_endpoints,
    market_decision_endpoints,
    signal_endpoints,
    strategy_endpoints,
)
from src.core.http.launch_modes import DeploymentProfile, LaunchMode


def build_router(*, mode: LaunchMode, profile: DeploymentProfile) -> APIRouter:
    del mode
    del profile
    router = APIRouter()
    router.include_router(signal_endpoints.router)
    router.include_router(decision_endpoints.router)
    router.include_router(market_decision_endpoints.router)
    router.include_router(final_signal_endpoints.router)
    router.include_router(backtest_endpoints.router)
    router.include_router(strategy_endpoints.router)
    return router
