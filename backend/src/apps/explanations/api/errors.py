from fastapi import HTTPException, status

from src.core.errors import ResourceNotFoundError
from src.core.http.errors import ApiError, ApiErrorFactory

_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_404_NOT_FOUND: "Requested explanation resource was not found.",
}


def explanation_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def signal_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="signal", locale=locale))


def decision_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="decision", locale=locale))


def explanation_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="explanation", locale=locale))


__all__ = [
    "decision_not_found_error",
    "explanation_error_responses",
    "explanation_not_found_error",
    "signal_not_found_error",
]
