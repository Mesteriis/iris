# ruff: noqa: RUF001

from __future__ import annotations

from src.apps.explanations.api.errors import (
    decision_not_found_error,
    explanation_not_found_error,
    signal_not_found_error,
)


def test_explanation_api_errors_use_localized_platform_payload() -> None:
    signal_error = signal_not_found_error(locale="ru")
    decision_error = decision_not_found_error(locale="en")
    explanation_error = explanation_not_found_error(locale="ru")

    assert signal_error.detail["message"] == "Запрошенный ресурс 'signal' не найден."
    assert signal_error.detail["domain"] == "api"
    assert signal_error.detail["category"] == "not_found"

    assert decision_error.detail["message"] == "The requested decision was not found."
    assert explanation_error.detail["message"] == "Запрошенный ресурс 'explanation' не найден."
