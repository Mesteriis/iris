# ruff: noqa: RUF001


from iris.apps.signals.api.errors import coin_not_found_error


def test_signal_coin_not_found_error_is_localized() -> None:
    error = coin_not_found_error(locale="ru")

    assert error.status_code == 404
    assert error.detail["message_key"] == "error.resource.not_found"
    assert error.detail["message"] == "Запрошенный ресурс 'coin' не найден."
