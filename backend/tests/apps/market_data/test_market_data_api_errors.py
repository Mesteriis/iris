# ruff: noqa: RUF001


from src.apps.market_data.api.errors import (
    MarketDataCoinConflictError,
    market_data_coin_not_found_error,
    market_data_error_to_http,
)


def test_market_data_api_errors_are_localized_from_registry() -> None:
    not_found = market_data_coin_not_found_error(locale="en")
    conflict = market_data_error_to_http(MarketDataCoinConflictError("btc"), locale="ru")

    assert not_found.status_code == 404
    assert not_found.detail["message"] == "The requested coin was not found."

    assert conflict is not None
    assert conflict.status_code == 409
    assert conflict.detail["code"] == "duplicate_request"
    assert conflict.detail["message"] == "Запрос конфликтует с уже существующим ресурсом."
