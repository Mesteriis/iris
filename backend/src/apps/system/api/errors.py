from typing import Any

from fastapi import HTTPException, status

from src.core.errors import ResourceNotFoundError
from src.core.http.errors import ApiError, ApiErrorFactory

_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_404_NOT_FOUND: "Requested operation resource was not found.",
}


def system_error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def operation_not_found_error(operation_id: str, *, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(
        ResourceNotFoundError(resource=f"operation '{operation_id}'", locale=locale),
        operation_id=operation_id,
    )


__all__ = [
    "operation_not_found_error",
    "system_error_responses",
]
