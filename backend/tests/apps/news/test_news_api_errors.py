# ruff: noqa: RUF001


from src.apps.news.api.errors import news_source_not_found_error, telegram_request_code_error
from src.apps.news.exceptions import TelegramOnboardingError


def test_news_api_errors_are_localized_from_registry() -> None:
    source_error = news_source_not_found_error(locale="ru")
    integration_error = telegram_request_code_error(TelegramOnboardingError(), locale="en")

    assert source_error.status_code == 404
    assert source_error.detail["message"] == "Запрошенный ресурс 'news source' не найден."

    assert integration_error.status_code == 503
    assert integration_error.detail["message_key"] == "error.integration.unreachable"
    assert integration_error.detail["message"] == "The required external integration is currently unavailable."
