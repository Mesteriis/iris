import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_ORIGINAL_SYS_PATH = list(sys.path)
sys.path = [
    path
    for path in _ORIGINAL_SYS_PATH
    if Path(path or ".").resolve() != _BACKEND_ROOT
]
import alembic.command as command
from alembic.config import Config

sys.path = _ORIGINAL_SYS_PATH
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import build_router as build_api_router
from src.core.http.launch_modes import resolve_deployment_profile, resolve_launch_mode
from src.core.http.router_policy import generate_operation_id
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
    async def deferred_lifespan(app: FastAPI) -> AsyncIterator[None]:
        from src.core.bootstrap.lifespan import lifespan

        async with lifespan(app):
            yield

    app = FastAPI(
        title=settings.app_name,
        lifespan=deferred_lifespan,
        generate_unique_id_function=generate_operation_id,
    )
    app.state.run_migrations = run_migrations
    app.state.api_launch_mode = resolve_launch_mode(settings.api_launch_mode)
    app.state.api_deployment_profile = resolve_deployment_profile(
        settings.api_deployment_profile,
        mode=app.state.api_launch_mode,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_api_router(settings))
    return app
