from __future__ import annotations

from collections.abc import Mapping

from fastapi import HTTPException, status

from src.apps.market_structure.exceptions import (
    InvalidMarketStructureSourceConfigurationError,
    InvalidMarketStructureWebhookPayloadError,
    UnauthorizedMarketStructureIngestError,
    UnsupportedMarketStructurePluginError,
)
from src.core.http.errors import ApiError, ApiErrorFactory


class MarketStructureSourceNotFoundError(Exception):
    def __init__(self, source_id: int) -> None:
        self.source_id = int(source_id)
        super().__init__(f"Market structure source '{self.source_id}' was not found.")


_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Request validation or market-structure domain policy failed.",
    status.HTTP_401_UNAUTHORIZED: "Source-level ingest authentication failed.",
    status.HTTP_404_NOT_FOUND: "Requested market-structure resource was not found.",
}


def market_structure_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def market_structure_source_not_found_error(source_id: int) -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message=f"Market structure source '{int(source_id)}' was not found.",
    )


def market_structure_error_to_http(exc: Exception) -> HTTPException | None:
    if isinstance(exc, MarketStructureSourceNotFoundError):
        return market_structure_source_not_found_error(exc.source_id)
    if isinstance(exc, (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError)):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_failed",
            message=str(exc),
        )
    if isinstance(exc, InvalidMarketStructureWebhookPayloadError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_failed",
            message=str(exc),
        )
    if isinstance(exc, UnauthorizedMarketStructureIngestError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="authentication_failed",
            message=str(exc),
        )
    return None


def market_structure_ingest_result_to_http(
    result: Mapping[str, object],
    *,
    source_id: int,
) -> HTTPException | None:
    result_status = str(result.get("status") or "").strip().lower()
    reason = str(result.get("reason") or "").strip().lower()
    if result_status == "error":
        if reason == "source_not_found":
            return market_structure_source_not_found_error(source_id)
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_state_transition",
            message=reason.replace("_", " ") or "Market structure ingest failed.",
        )
    if result_status == "skipped":
        message = {
            "plugin_does_not_support_manual_ingest": "Source does not support manual ingest.",
        }.get(reason, reason.replace("_", " ") or "Market structure ingest was skipped.")
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_state_transition",
            message=message,
        )
    return None


__all__ = [
    "MarketStructureSourceNotFoundError",
    "market_structure_error_responses",
    "market_structure_error_to_http",
    "market_structure_ingest_result_to_http",
    "market_structure_source_not_found_error",
]
