from collections.abc import Mapping

from iris.core.i18n.contracts import LocalePolicy, LocaleResolution
from iris.core.i18n.locale import normalize_locale, resolve_locale
from iris.core.i18n.locale_policy import build_locale_policy
from iris.core.settings import Settings


def normalize_language(value: str | None, *, settings: Settings | None = None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    policy: LocalePolicy = build_locale_policy(settings=settings)
    return normalize_locale(normalized, policy=policy) or policy.fallback_locale


def resolve_requested_language(
    ctx: Mapping[str, object],
    *,
    settings: Settings | None = None,
) -> str | None:
    for key in ("language", "locale"):
        normalized = normalize_language(_string_or_none(ctx.get(key)), settings=settings)
        if normalized is not None:
            return normalized
    return None


def resolve_effective_language(
    ctx: Mapping[str, object],
    *,
    settings: Settings | None = None,
) -> str:
    policy: LocalePolicy = build_locale_policy(settings=settings)
    requested = resolve_requested_language(ctx, settings=settings)
    resolution: LocaleResolution = resolve_locale(explicit_locale=requested, policy=policy)
    return resolution.effective_locale


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "normalize_language",
    "resolve_effective_language",
    "resolve_requested_language",
]
