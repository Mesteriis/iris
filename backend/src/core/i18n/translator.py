from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from types import MappingProxyType

from src.core.i18n.catalogs.en import TRANSLATIONS as EN_TRANSLATIONS
from src.core.i18n.catalogs.ru import TRANSLATIONS as RU_TRANSLATIONS
from src.core.i18n.contracts import LocalePolicy, LocalizedText
from src.core.i18n.locale import DEFAULT_LOCALE_POLICY, resolve_locale


class TranslationError(ValueError):
    """Base error for deterministic translation failures."""


class MissingTranslationKeyError(TranslationError):
    def __init__(self, *, key: str, locales: tuple[str, ...]) -> None:
        super().__init__(f"Translation key '{key}' is not registered for locales: {', '.join(locales)}.")
        self.key = key
        self.locales = locales


class TranslationInterpolationError(TranslationError):
    def __init__(self, *, key: str, locale: str, missing_param: str) -> None:
        super().__init__(f"Translation key '{key}' for locale '{locale}' is missing param '{missing_param}'.")
        self.key = key
        self.locale = locale
        self.missing_param = missing_param


class TranslationService:
    def __init__(
        self,
        *,
        catalogs: Mapping[str, Mapping[str, str]],
        policy: LocalePolicy = DEFAULT_LOCALE_POLICY,
    ) -> None:
        self._policy = policy
        self._catalogs = {
            locale: MappingProxyType(dict(catalog))
            for locale, catalog in catalogs.items()
        }

    @property
    def policy(self) -> LocalePolicy:
        return self._policy

    def translate(
        self,
        key: str,
        *,
        locale: str | None = None,
        accept_language: str | None = None,
        params: Mapping[str, object] | None = None,
    ) -> LocalizedText:
        resolution = resolve_locale(
            explicit_locale=locale,
            accept_language=accept_language,
            policy=self._policy,
        )
        render_params = dict(params or {})
        for candidate in resolution.fallback_chain:
            catalog = self._catalogs.get(candidate)
            if catalog is None or key not in catalog:
                continue
            template = catalog[key]
            try:
                text = template.format_map(_StrictFormatDict(render_params))
            except KeyError as exc:
                missing_param = str(exc.args[0])
                raise TranslationInterpolationError(
                    key=key,
                    locale=candidate,
                    missing_param=missing_param,
                ) from exc
            fallback_locale = candidate if candidate != resolution.effective_locale else None
            return LocalizedText(
                key=key,
                locale=resolution.effective_locale,
                text=text,
                params=render_params,
                fallback_locale=fallback_locale,
            )
        raise MissingTranslationKeyError(key=key, locales=resolution.fallback_chain)


@lru_cache(maxsize=1)
def get_translation_service() -> TranslationService:
    return TranslationService(
        catalogs={
            "en": EN_TRANSLATIONS,
            "ru": RU_TRANSLATIONS,
        }
    )


class _StrictFormatDict(dict[str, object]):
    def __missing__(self, key: str) -> object:
        raise KeyError(key)
