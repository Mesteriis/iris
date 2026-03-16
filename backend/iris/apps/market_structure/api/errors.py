from typing import Any

from fastapi import HTTPException, status

from iris.apps.market_structure.exceptions import (
    InvalidMarketStructureSourceConfigurationError,
    InvalidMarketStructureWebhookPayloadError,
    UnauthorizedMarketStructureIngestError,
    UnsupportedMarketStructurePluginError,
)
from iris.apps.market_structure.services.results import MarketStructureIngestResult
from iris.core.errors import (
    AuthenticationFailedError,
    InvalidStateTransitionError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from iris.core.http.errors import ApiError, ApiErrorFactory


class MarketStructureSourceNotFoundError(Exception):
    def __init__(self, source_id: int) -> None:
        self.source_id = int(source_id)
        super().__init__(f"Market structure source '{self.source_id}' was not found.")


_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Request validation or market-structure domain policy failed.",
    status.HTTP_401_UNAUTHORIZED: "Source-level ingest authentication failed.",
    status.HTTP_404_NOT_FOUND: "Requested market-structure resource was not found.",
}


def market_structure_error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def market_structure_source_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="market structure source", locale=locale))


def market_structure_error_to_http(exc: Exception, *, locale: str) -> HTTPException | None:
    if isinstance(exc, MarketStructureSourceNotFoundError):
        return market_structure_source_not_found_error(locale=locale)
    if isinstance(exc, InvalidMarketStructureSourceConfigurationError | UnsupportedMarketStructurePluginError):
        return ApiErrorFactory.from_platform_error(ValidationFailedError(locale=locale))
    if isinstance(exc, InvalidMarketStructureWebhookPayloadError):
        return ApiErrorFactory.from_platform_error(ValidationFailedError(locale=locale))
    if isinstance(exc, UnauthorizedMarketStructureIngestError):
        return ApiErrorFactory.from_platform_error(AuthenticationFailedError(locale=locale))
    return None


def market_structure_ingest_result_to_http(
    result: MarketStructureIngestResult,
    *,
    source_id: int,
    locale: str,
) -> HTTPException | None:
    result_status = str(result.status or "").strip().lower()
    reason = str(result.reason or "").strip().lower()
    if result_status == "error":
        if reason == "source_not_found":
            return market_structure_source_not_found_error(locale=locale)
        return ApiErrorFactory.from_platform_error(InvalidStateTransitionError(locale=locale))
    if result_status == "skipped":
        return ApiErrorFactory.from_platform_error(InvalidStateTransitionError(locale=locale))
    return None


__all__ = [
    "MarketStructureSourceNotFoundError",
    "market_structure_error_responses",
    "market_structure_error_to_http",
    "market_structure_ingest_result_to_http",
    "market_structure_source_not_found_error",
]
