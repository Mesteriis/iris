import pytest
from src.core.i18n import (
    LocalePolicy,
    TranslationInterpolationError,
    TranslationService,
    load_catalog,
    resolve_locale,
)


def test_resolve_locale_prefers_explicit_override() -> None:
    resolution = resolve_locale(explicit_locale="ru-RU")

    assert resolution.requested_locale == "ru"
    assert resolution.effective_locale == "ru"
    assert resolution.fallback_chain == ("ru", "en")
    assert resolution.source == "explicit"


def test_external_catalog_contains_versioned_entries() -> None:
    catalog = load_catalog("en")

    assert catalog.version == 1
    assert catalog.messages["error.resource.not_found"].message == "The requested {resource} was not found."
    assert catalog.messages["error.resource.not_found"].description


def test_translation_service_falls_back_to_default_locale_catalog() -> None:
    service = TranslationService(
        catalogs={
            "en": {"error.test": "Hello {name}."},
            "ru": {},
        },
        policy=LocalePolicy(supported_locales=("en", "ru"), default_locale="en", fallback_locale="en"),
    )

    localized = service.translate("error.test", locale="ru", params={"name": "IRIS"})

    assert localized.locale == "ru"
    assert localized.text == "Hello IRIS."
    assert localized.fallback_locale == "en"


def test_translation_service_rejects_missing_interpolation_params() -> None:
    service = TranslationService(
        catalogs={"en": {"error.test": "Hello {name}."}},
        policy=LocalePolicy(supported_locales=("en",), default_locale="en", fallback_locale="en"),
    )

    with pytest.raises(TranslationInterpolationError, match="missing param 'name'"):
        service.translate("error.test", locale="en")
