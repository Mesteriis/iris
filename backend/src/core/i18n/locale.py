from __future__ import annotations

from collections.abc import Iterable

from src.core.i18n.contracts import LocalePolicy, LocaleResolution

DEFAULT_LOCALE_POLICY = LocalePolicy()
LOCALE_ALIASES: dict[str, str] = {
    "ua": "uk",
}


def normalize_locale(value: str | None, *, policy: LocalePolicy = DEFAULT_LOCALE_POLICY) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("_", "-")
    if not normalized:
        return None
    primary = normalized.split("-", maxsplit=1)[0]
    primary = LOCALE_ALIASES.get(primary, primary)
    return primary if primary in policy.supported_locales else None


def parse_accept_language(header: str | None, *, policy: LocalePolicy = DEFAULT_LOCALE_POLICY) -> tuple[str, ...]:
    if header is None or not str(header).strip():
        return ()

    weighted_candidates: list[tuple[float, int, str]] = []
    for position, raw_part in enumerate(str(header).split(",")):
        segment = raw_part.strip()
        if not segment:
            continue
        language = segment
        weight = 1.0
        if ";" in segment:
            language, *params = (item.strip() for item in segment.split(";"))
            for parameter in params:
                if parameter.startswith("q="):
                    try:
                        weight = float(parameter[2:])
                    except ValueError:
                        weight = 0.0
        normalized = normalize_locale(language, policy=policy)
        if normalized is None:
            continue
        weighted_candidates.append((weight, position, normalized))

    weighted_candidates.sort(key=lambda item: (-item[0], item[1]))
    ordered = [candidate for _, _, candidate in weighted_candidates]
    return _deduplicate(ordered)


def resolve_locale(
    *,
    explicit_locale: str | None = None,
    accept_language: str | None = None,
    policy: LocalePolicy = DEFAULT_LOCALE_POLICY,
) -> LocaleResolution:
    requested_locale = normalize_locale(explicit_locale, policy=policy)
    accept_language_chain = parse_accept_language(accept_language, policy=policy)

    if requested_locale is not None:
        effective_locale = requested_locale
        source = "explicit"
    elif accept_language_chain:
        effective_locale = accept_language_chain[0]
        source = "accept_language"
    else:
        effective_locale = policy.default_locale
        source = "default"

    fallback_chain = (effective_locale,)
    if policy.fallback_locale != effective_locale:
        fallback_chain = (effective_locale, policy.fallback_locale)

    return LocaleResolution(
        requested_locale=requested_locale,
        effective_locale=effective_locale,
        fallback_chain=fallback_chain,
        source=source,
        accept_language_chain=accept_language_chain,
    )


def _deduplicate(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)
