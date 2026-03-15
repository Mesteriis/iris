from __future__ import annotations

from fastapi import HTTPException, status

from src.core.errors import ResourceNotFoundError
from src.core.http.errors import ApiError, ApiErrorFactory

_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_404_NOT_FOUND: "Requested brief resource was not found.",
}


def brief_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def symbol_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="symbol", locale=locale))


def brief_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="brief", locale=locale))


__all__ = [
    "brief_error_responses",
    "brief_not_found_error",
    "symbol_not_found_error",
]
