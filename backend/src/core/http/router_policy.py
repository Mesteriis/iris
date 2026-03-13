from __future__ import annotations

from src.core.settings import get_settings


def normalize_path_prefix(value: str) -> str:
    if not value:
        return ""
    normalized = value.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized.rstrip("/")


def api_path(path: str) -> str:
    settings = get_settings()
    root = normalize_path_prefix(settings.api_root_prefix)
    version = normalize_path_prefix(settings.api_version_prefix)
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{root}{version}{suffix}"
