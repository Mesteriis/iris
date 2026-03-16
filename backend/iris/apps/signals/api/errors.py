from typing import Any

from fastapi import HTTPException, status

from iris.core.errors import ResourceNotFoundError
from iris.core.http.errors import ApiError, ApiErrorFactory


def signal_error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    descriptions = {
        status.HTTP_404_NOT_FOUND: "Requested signal resource was not found.",
    }
    return {
        int(status_code): {
            "model": ApiError,
            "description": descriptions[int(status_code)],
        }
        for status_code in status_codes
    }


def coin_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="coin", locale=locale))


__all__ = ["coin_not_found_error", "signal_error_responses"]
