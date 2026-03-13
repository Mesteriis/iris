from __future__ import annotations

from fastapi import HTTPException, status

from src.apps.news.exceptions import InvalidNewsSourceConfigurationError, TelegramOnboardingError, UnsupportedNewsPluginError
from src.core.http.errors import ApiError, ApiErrorFactory


class NewsSourceNotFoundError(Exception):
    def __init__(self, source_id: int) -> None:
        self.source_id = int(source_id)
        super().__init__(f"News source '{self.source_id}' was not found.")


_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Request validation or news-domain policy failed.",
    status.HTTP_404_NOT_FOUND: "Requested news resource was not found.",
    status.HTTP_503_SERVICE_UNAVAILABLE: "Required onboarding integration is unavailable.",
}


def news_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def news_source_not_found_error(source_id: int) -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message=f"News source '{int(source_id)}' was not found.",
    )


def news_error_to_http(exc: Exception) -> HTTPException | None:
    if isinstance(exc, NewsSourceNotFoundError):
        return news_source_not_found_error(exc.source_id)
    if isinstance(exc, (InvalidNewsSourceConfigurationError, UnsupportedNewsPluginError)):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_failed",
            message=str(exc),
        )
    return None


def telegram_request_code_error(exc: TelegramOnboardingError) -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="integration_unreachable",
        message=str(exc),
    )


def telegram_onboarding_error(exc: TelegramOnboardingError) -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="validation_failed",
        message=str(exc),
    )


__all__ = [
    "NewsSourceNotFoundError",
    "news_error_responses",
    "news_error_to_http",
    "news_source_not_found_error",
    "telegram_onboarding_error",
    "telegram_request_code_error",
]
