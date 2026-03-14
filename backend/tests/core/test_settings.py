from __future__ import annotations

import pytest
from pydantic import ValidationError
from src.core.settings import AppLanguage, Settings


def test_settings_accept_supported_language_alias() -> None:
    settings = Settings(IRIS_LANGUAGE="es")

    assert settings.language is AppLanguage.ES


def test_settings_reject_unsupported_language() -> None:
    with pytest.raises(ValidationError):
        Settings(IRIS_LANGUAGE="de")


def test_settings_parse_ai_provider_registry_and_capability_overrides() -> None:
    settings = Settings(
        IRIS_AI_PROVIDERS='[{"name":"local_test","kind":"local_http","enabled":true,"base_url":"http://127.0.0.1:11434","model":"llama3","capabilities":["hypothesis_generate"]}]',
        IRIS_AI_CAPABILITIES='{"hypothesis_generate":{"allow_degraded_fallback":true}}',
    )

    assert settings.ai_providers[0]["name"] == "local_test"
    assert settings.ai_providers[0]["capabilities"] == ["hypothesis_generate"]
    assert settings.ai_capabilities["hypothesis_generate"]["allow_degraded_fallback"] is True
