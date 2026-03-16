from src.core.i18n import normalize_language, resolve_effective_language, resolve_requested_language
from src.core.settings import Settings


def test_context_language_normalization_falls_back_to_rollout_default() -> None:
    assert normalize_language("es") == "en"


def test_context_requested_language_uses_supported_request_value() -> None:
    assert resolve_requested_language({"language": "ru-RU"}) == "ru"


def test_context_effective_language_uses_global_settings_default() -> None:
    assert resolve_effective_language({}, settings=Settings(IRIS_LANGUAGE="ru")) == "ru"
