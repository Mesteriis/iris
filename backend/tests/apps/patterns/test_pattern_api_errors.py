# ruff: noqa: RUF001


from src.apps.patterns.api.errors import PatternNotFoundError, pattern_coin_not_found_error, pattern_error_to_http


def test_pattern_api_errors_are_localized_from_registry() -> None:
    coin_error = pattern_coin_not_found_error(locale="ru")
    pattern_error = pattern_error_to_http(PatternNotFoundError("breakout"), locale="en")

    assert coin_error.status_code == 404
    assert coin_error.detail["message"] == "Запрошенный ресурс 'coin' не найден."

    assert pattern_error is not None
    assert pattern_error.detail["message_key"] == "error.resource.not_found"
    assert pattern_error.detail["message"] == "Pattern 'breakout' was not found."
    assert pattern_error.detail["message_params"] == {"resource": "pattern"}
