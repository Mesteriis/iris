from fastapi import HTTPException, status

from src.core.errors import ResourceNotFoundError, ValidationFailedError
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


def pattern_coin_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="coin", locale=locale))


def pattern_error_to_http(exc: Exception, *, locale: str) -> HTTPException | None:
    if isinstance(exc, PatternFeatureNotFoundError):
        return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="pattern feature", locale=locale))
    if isinstance(exc, PatternNotFoundError):
        return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="pattern", locale=locale))
    if isinstance(exc, ValueError):
        return ApiErrorFactory.from_platform_error(ValidationFailedError(locale=locale))
    return None


__all__ = [
    "PatternFeatureNotFoundError",
    "PatternNotFoundError",
    "pattern_coin_not_found_error",
    "pattern_error_responses",
    "pattern_error_to_http",
]
