# ruff: noqa: RUF001

from __future__ import annotations

from src.apps.briefs.api.errors import brief_not_found_error, symbol_not_found_error


def test_brief_api_errors_are_localized_from_registry() -> None:
    brief_error = brief_not_found_error(locale="ru")
    symbol_error = symbol_not_found_error(locale="en")

    assert brief_error.status_code == 404
    assert brief_error.detail["message_key"] == "errors.generic.resource_not_found"
    assert brief_error.detail["locale"] == "ru"
    assert brief_error.detail["message"] == "Запрошенный ресурс 'brief' не найден."

    assert symbol_error.status_code == 404
    assert symbol_error.detail["message"] == "The requested symbol was not found."
    assert symbol_error.detail["message_params"] == {"resource": "symbol"}
