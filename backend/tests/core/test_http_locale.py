from __future__ import annotations

from src.core.http.deps import build_request_locale_policy, resolve_request_locale
from src.core.settings import Settings
from starlette.requests import Request


def test_request_locale_uses_settings_default_when_request_has_no_locale() -> None:
    request = _build_request()

    resolved = resolve_request_locale(request, settings=Settings(IRIS_LANGUAGE="ru"))

    assert resolved == "ru"


def test_request_locale_prefers_header_override_and_accept_language() -> None:
    request = _build_request(headers={"x-iris-locale": "ru", "accept-language": "en-US,en;q=0.9"})

    resolved = resolve_request_locale(request, settings=Settings(IRIS_LANGUAGE="en"))

    assert resolved == "ru"


def test_request_locale_policy_limits_supported_locales_to_current_rollout() -> None:
    policy = build_request_locale_policy(settings=Settings(IRIS_LANGUAGE="en"))

    assert policy.supported_locales == ("en", "ru")
    assert policy.fallback_locale == "en"


def _build_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/test",
            "headers": raw_headers,
            "query_string": b"",
        }
    )
