from typing import Any

from fastapi import HTTPException, status

from iris.apps.news.exceptions import (
    InvalidNewsSourceConfigurationError,
    TelegramOnboardingError,
    UnsupportedNewsPluginError,
)
from iris.core.errors import IntegrationUnreachableError, ResourceNotFoundError, ValidationFailedError
from iris.core.http.errors import ApiError, ApiErrorFactory


class NewsSourceNotFoundError(Exception):
    def __init__(self, source_id: int) -> None:
        self.source_id = int(source_id)
        super().__init__(f"News source '{self.source_id}' was not found.")


_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Request validation or news-domain policy failed.",
    status.HTTP_404_NOT_FOUND: "Requested news resource was not found.",
    status.HTTP_503_SERVICE_UNAVAILABLE: "Required onboarding integration is unavailable.",
}


def news_error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def news_source_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="news source", locale=locale))


def news_error_to_http(exc: Exception, *, locale: str) -> HTTPException | None:
    if isinstance(exc, NewsSourceNotFoundError):
        return news_source_not_found_error(locale=locale)
    if isinstance(exc, InvalidNewsSourceConfigurationError | UnsupportedNewsPluginError):
        return ApiErrorFactory.from_platform_error(ValidationFailedError(locale=locale))
    return None


def telegram_request_code_error(exc: TelegramOnboardingError, *, locale: str) -> HTTPException:
    del exc
    return ApiErrorFactory.from_platform_error(IntegrationUnreachableError(locale=locale))


def telegram_onboarding_error(exc: TelegramOnboardingError, *, locale: str) -> HTTPException:
    del exc
    return ApiErrorFactory.from_platform_error(ValidationFailedError(locale=locale))


__all__ = [
    "NewsSourceNotFoundError",
    "news_error_responses",
    "news_error_to_http",
    "news_source_not_found_error",
    "telegram_onboarding_error",
    "telegram_request_code_error",
]
