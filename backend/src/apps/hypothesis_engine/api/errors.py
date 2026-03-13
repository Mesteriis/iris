from __future__ import annotations

from fastapi import HTTPException, status

from src.apps.hypothesis_engine.exceptions import InvalidPromptPayloadError, PromptNotFoundError
from src.core.http.errors import ApiError, ApiErrorFactory

_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Request validation or hypothesis prompt policy failed.",
    status.HTTP_404_NOT_FOUND: "Requested hypothesis resource was not found.",
}


def hypothesis_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def hypothesis_error_to_http(exc: Exception) -> HTTPException | None:
    if isinstance(exc, InvalidPromptPayloadError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_failed",
            message=str(exc),
        )
    if isinstance(exc, PromptNotFoundError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message=str(exc),
        )
    return None


__all__ = ["hypothesis_error_responses", "hypothesis_error_to_http"]
