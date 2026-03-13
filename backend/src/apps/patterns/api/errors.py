from __future__ import annotations

from fastapi import HTTPException, status

from src.core.http.errors import ApiError, ApiErrorFactory


class PatternFeatureNotFoundError(Exception):
    def __init__(self, feature_slug: str) -> None:
        self.feature_slug = feature_slug
        super().__init__(f"Pattern feature '{feature_slug}' was not found.")


class PatternNotFoundError(Exception):
    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"Pattern '{slug}' was not found.")


_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Request validation or pattern-domain policy failed.",
    status.HTTP_404_NOT_FOUND: "Requested pattern resource was not found.",
}


def pattern_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def pattern_coin_not_found_error(symbol: str) -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message=f"Coin '{symbol.upper()}' was not found.",
    )


def pattern_error_to_http(exc: Exception) -> HTTPException | None:
    if isinstance(exc, PatternFeatureNotFoundError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message=str(exc),
        )
    if isinstance(exc, PatternNotFoundError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message=str(exc),
        )
    if isinstance(exc, ValueError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_failed",
            message=str(exc),
        )
    return None


__all__ = [
    "PatternFeatureNotFoundError",
    "PatternNotFoundError",
    "pattern_coin_not_found_error",
    "pattern_error_responses",
    "pattern_error_to_http",
]
