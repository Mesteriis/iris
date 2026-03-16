from difflib import unified_diff
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


def read_openapi_schema(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def diff_openapi_schema(*, settings: Settings, snapshot: str | Path) -> str:
    snapshot_path = Path(snapshot)
    expected = read_openapi_schema(snapshot_path)
    actual = f"{dump_openapi_schema(settings)}\n"
    if actual == expected:
        return ""
    return "".join(
        unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=str(snapshot_path),
            tofile=f"{snapshot_path}.generated",
        )
    )


def check_openapi_schema(*, settings: Settings, snapshot: str | Path) -> tuple[bool, str]:
    diff = diff_openapi_schema(settings=settings, snapshot=snapshot)
    return diff == "", diff


def write_openapi_schema(*, settings: Settings, output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{dump_openapi_schema(settings)}\n", encoding="utf-8")
    return output_path


__all__ = [
    "build_openapi_app",
    "build_openapi_schema",
    "check_openapi_schema",
    "diff_openapi_schema",
    "dump_openapi_schema",
    "read_openapi_schema",
    "write_openapi_schema",
]
