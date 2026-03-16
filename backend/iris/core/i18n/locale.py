from iris.core.i18n.contracts import LocalePolicy, LocaleResolution

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


def resolve_locale(
    *,
    explicit_locale: str | None = None,
    policy: LocalePolicy = DEFAULT_LOCALE_POLICY,
) -> LocaleResolution:
    requested_locale = normalize_locale(explicit_locale, policy=policy)

    if requested_locale is not None:
        effective_locale = requested_locale
        source = "explicit"
    else:
        effective_locale = policy.default_locale
        source = "default"

    fallback_chain: tuple[str, ...] = (effective_locale,)
    if policy.fallback_locale != effective_locale:
        fallback_chain = (effective_locale, policy.fallback_locale)

    return LocaleResolution(
        requested_locale=requested_locale,
        effective_locale=effective_locale,
        fallback_chain=fallback_chain,
        source=source,
    )
