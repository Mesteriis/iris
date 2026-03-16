from fastapi import HTTPException, status

from src.core.errors import ResourceNotFoundError
from src.core.http.errors import ApiError, ApiErrorFactory

_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_404_NOT_FOUND: "Requested notification resource was not found.",
}


def notification_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def notification_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="notification", locale=locale))


__all__ = [
    "notification_error_responses",
    "notification_not_found_error",
]
