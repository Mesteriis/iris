from src.core.i18n.contracts import LocalePolicy
from src.core.i18n.locale import normalize_locale
from src.core.settings import Settings, get_settings

SUPPORTED_LOCALES: tuple[str, ...] = ("en", "ru")
FALLBACK_LOCALE = "en"


def build_locale_policy(*, settings: Settings | None = None) -> LocalePolicy:
    effective_settings = settings or get_settings()
    base_policy = LocalePolicy(
        supported_locales=SUPPORTED_LOCALES,
        default_locale=FALLBACK_LOCALE,
        fallback_locale=FALLBACK_LOCALE,
    )
    default_locale = normalize_locale(
        getattr(effective_settings.language, "value", effective_settings.language),
        policy=base_policy,
    ) or FALLBACK_LOCALE
    return LocalePolicy(
        supported_locales=SUPPORTED_LOCALES,
        default_locale=default_locale,
        fallback_locale=FALLBACK_LOCALE,
    )
