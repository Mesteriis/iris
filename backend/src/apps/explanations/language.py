from __future__ import annotations

from typing import Any

from src.core.settings import Settings, get_settings

_SUPPORTED_LANGUAGES = {"en", "ru", "es", "uk"}
_LANGUAGE_ALIASES = {"ua": "uk"}


def normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("_", "-")
    if not normalized:
        return None
    normalized = _LANGUAGE_ALIASES.get(normalized, normalized)
    primary = normalized.split("-", maxsplit=1)[0]
    if primary in _LANGUAGE_ALIASES:
        primary = _LANGUAGE_ALIASES[primary]
    return primary if primary in _SUPPORTED_LANGUAGES else "en"


def resolve_requested_language(ctx: dict[str, Any]) -> str | None:
    for key in ("language", "locale"):
        normalized = normalize_language(ctx.get(key))
        if normalized is not None:
            return normalized
    return None


def resolve_effective_language(ctx: dict[str, Any], *, settings: Settings | None = None) -> str:
    requested = resolve_requested_language(ctx)
    if requested is not None:
        return requested
    effective_settings = settings or get_settings()
    default_language = normalize_language(getattr(effective_settings.language, "value", effective_settings.language))
    return default_language or "en"


__all__ = ["normalize_language", "resolve_effective_language", "resolve_requested_language"]
