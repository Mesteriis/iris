from __future__ import annotations

import pytest
from src.core.i18n import (
    LocalePolicy,
    TranslationInterpolationError,
    TranslationService,
    parse_accept_language,
    resolve_locale,
)


def test_resolve_locale_prefers_explicit_override() -> None:
    resolution = resolve_locale(explicit_locale="ru-RU", accept_language="en-US,en;q=0.8")

    assert resolution.requested_locale == "ru"
    assert resolution.effective_locale == "ru"
    assert resolution.fallback_chain == ("ru", "en")
    assert resolution.source == "explicit"


def test_parse_accept_language_keeps_supported_candidates_in_priority_order() -> None:
    candidates = parse_accept_language("de-DE,de;q=0.9,ru-RU;q=0.8,en-US;q=0.7")

    assert candidates == ("ru", "en")


def test_translation_service_falls_back_to_default_locale_catalog() -> None:
    service = TranslationService(
        catalogs={
            "en": {"errors.test": "Hello {name}."},
            "ru": {},
        },
        policy=LocalePolicy(supported_locales=("en", "ru"), default_locale="en", fallback_locale="en"),
    )

    localized = service.translate("errors.test", locale="ru", params={"name": "IRIS"})

    assert localized.locale == "ru"
    assert localized.text == "Hello IRIS."
    assert localized.fallback_locale == "en"


def test_translation_service_rejects_missing_interpolation_params() -> None:
    service = TranslationService(
        catalogs={"en": {"errors.test": "Hello {name}."}},
        policy=LocalePolicy(supported_locales=("en",), default_locale="en", fallback_locale="en"),
    )

    with pytest.raises(TranslationInterpolationError, match="missing param 'name'"):
        service.translate("errors.test", locale="en")
