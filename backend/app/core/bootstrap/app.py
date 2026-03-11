from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.apps.indicators.views import router as indicators_router
from app.apps.market_data.views import router as market_data_router
from app.apps.patterns.views import router as patterns_router
from app.apps.portfolio.views import router as portfolio_router
from app.apps.predictions.views import router as predictions_router
from app.apps.signals.views import router as signals_router
from app.apps.system.views import router as system_router
from app.core.settings import get_settings

settings = get_settings()


def get_alembic_config() -> Config:
    alembic_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    config = Config(str(alembic_path))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[3] / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def run_migrations() -> None:
    command.upgrade(get_alembic_config(), "head")


def create_app() -> FastAPI:
    @asynccontextmanager
    async def deferred_lifespan(app: FastAPI):
        from app.core.bootstrap.lifespan import lifespan

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
    app.include_router(indicators_router)
    app.include_router(patterns_router)
    app.include_router(signals_router)
    app.include_router(portfolio_router)
    app.include_router(predictions_router)
    return app
