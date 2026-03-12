from __future__ import annotations

import sys
from pathlib import Path
from contextlib import asynccontextmanager

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_ORIGINAL_SYS_PATH = list(sys.path)
sys.path = [
    path
    for path in _ORIGINAL_SYS_PATH
    if Path(path or ".").resolve() != _BACKEND_ROOT
]
from alembic.config import Config
import alembic.command as command
sys.path = _ORIGINAL_SYS_PATH
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.apps.indicators.views import router as indicators_router
from src.apps.market_data.views import router as market_data_router
from src.apps.market_structure.views import router as market_structure_router
from src.apps.news.views import router as news_router
from src.apps.patterns.views import router as patterns_router
from src.apps.portfolio.views import router as portfolio_router
from src.apps.predictions.views import router as predictions_router
from src.apps.hypothesis_engine.views import router as hypothesis_router
from src.apps.signals.views import router as signals_router
from src.apps.system.views import router as system_router
from src.core.settings import get_settings

settings = get_settings()


def get_alembic_config() -> Config:
    alembic_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    config = Config(str(alembic_path))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[3] / "src" / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def run_migrations() -> None:
    command.upgrade(get_alembic_config(), "head")


def create_app() -> FastAPI:
    @asynccontextmanager
    async def deferred_lifespan(app: FastAPI):
        from src.core.bootstrap.lifespan import lifespan

        async with lifespan(app):
            yield

    app = FastAPI(title=settings.app_name, lifespan=deferred_lifespan)
    app.state.run_migrations = run_migrations

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system_router)
    app.include_router(market_data_router)
    app.include_router(market_structure_router)
    app.include_router(news_router)
    app.include_router(indicators_router)
    app.include_router(patterns_router)
    app.include_router(signals_router)
    app.include_router(portfolio_router)
    app.include_router(predictions_router)
    if settings.enable_hypothesis_engine:
        app.include_router(hypothesis_router)
    return app
