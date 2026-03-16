from typing import Any

from fastapi import HTTPException, status

from iris.apps.hypothesis_engine.exceptions import (
    InvalidPromptPayloadError,
    PromptNotFoundError,
    PromptVeilLockedError,
)
from iris.core.errors import PromptVeilLockedPlatformError, ResourceNotFoundError, ValidationFailedError
from iris.core.http.errors import ApiError, ApiErrorFactory

_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Request validation or hypothesis prompt policy failed.",
    status.HTTP_404_NOT_FOUND: "Requested hypothesis resource was not found.",
    status.HTTP_423_LOCKED: "Requested prompt family is veiled and cannot be edited yet.",
}


def hypothesis_error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def hypothesis_error_to_http(exc: Exception, *, locale: str) -> HTTPException | None:
    if isinstance(exc, InvalidPromptPayloadError):
        return ApiErrorFactory.from_platform_error(ValidationFailedError(locale=locale))
    if isinstance(exc, PromptNotFoundError):
        return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="prompt", locale=locale))
    if isinstance(exc, PromptVeilLockedError):
        return ApiErrorFactory.from_platform_error(PromptVeilLockedPlatformError(locale=locale))
    return None


__all__ = ["hypothesis_error_responses", "hypothesis_error_to_http"]
