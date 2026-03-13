from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from src.api.router import build_router as build_api_router
from src.core.http.launch_modes import resolve_deployment_profile, resolve_launch_mode
from src.core.http.router_policy import generate_operation_id
from src.core.settings import Settings


def build_openapi_app(settings: Settings) -> FastAPI:
    mode = resolve_launch_mode(settings.api_launch_mode)
    profile = resolve_deployment_profile(settings.api_deployment_profile, mode=mode)
    app = FastAPI(title=settings.app_name, generate_unique_id_function=generate_operation_id)
    app.state.api_launch_mode = mode
    app.state.api_deployment_profile = profile
    app.include_router(build_api_router(settings))
    return app


def build_openapi_schema(settings: Settings) -> dict[str, Any]:
    return build_openapi_app(settings).openapi()


def dump_openapi_schema(settings: Settings) -> str:
    return json.dumps(build_openapi_schema(settings), indent=2, sort_keys=True)


def write_openapi_schema(*, settings: Settings, output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{dump_openapi_schema(settings)}\n", encoding="utf-8")
    return output_path


__all__ = [
    "build_openapi_app",
    "build_openapi_schema",
    "dump_openapi_schema",
    "write_openapi_schema",
]
