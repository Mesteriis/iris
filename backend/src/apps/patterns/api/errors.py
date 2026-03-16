from typing import Any

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


def pattern_error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def pattern_coin_not_found_error(*, locale: str, symbol: str | None = None) -> HTTPException:
    if symbol is None:
        return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="coin", locale=locale))
    return _pattern_not_found_http_error(
        message=f"Coin '{symbol.strip().upper()}' was not found.",
        resource="coin",
        locale=locale,
    )


def _pattern_not_found_http_error(*, message: str, resource: str, locale: str) -> HTTPException:
    platform_error = ResourceNotFoundError(resource=resource, locale=locale)
    payload = ApiErrorFactory.build_from_platform_error(platform_error, locale=locale).model_copy(
        update={"message": message}
    )
    return HTTPException(
        status_code=platform_error.http_status,
        detail=payload.model_dump(mode="json"),
    )


def _pattern_validation_http_error(*, message: str, locale: str) -> HTTPException:
    platform_error = ValidationFailedError(locale=locale)
    payload = ApiErrorFactory.build_from_platform_error(platform_error, locale=locale).model_copy(
        update={"message": message}
    )
    return HTTPException(
        status_code=platform_error.http_status,
        detail=payload.model_dump(mode="json"),
    )


def pattern_error_to_http(exc: Exception, *, locale: str) -> HTTPException | None:
    if isinstance(exc, PatternFeatureNotFoundError):
        return _pattern_not_found_http_error(
            message=str(exc),
            resource="pattern feature",
            locale=locale,
        )
    if isinstance(exc, PatternNotFoundError):
        return _pattern_not_found_http_error(
            message=str(exc),
            resource="pattern",
            locale=locale,
        )
    if isinstance(exc, ValueError):
        return _pattern_validation_http_error(message=str(exc), locale=locale)
    return None


__all__ = [
    "PatternFeatureNotFoundError",
    "PatternNotFoundError",
    "pattern_coin_not_found_error",
    "pattern_error_responses",
    "pattern_error_to_http",
]
