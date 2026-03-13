from __future__ import annotations

from fastapi import HTTPException, status

from src.core.http.errors import ApiError, ApiErrorFactory

_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_404_NOT_FOUND: "Requested operation resource was not found.",
}


def system_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def operation_not_found_error(operation_id: str) -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message=f"Operation '{operation_id}' was not found.",
        operation_id=operation_id,
    )


__all__ = [
    "operation_not_found_error",
    "system_error_responses",
]
