from __future__ import annotations

from fastapi import HTTPException, status

from src.core.http.errors import ApiError, ApiErrorFactory


class MarketDataCoinNotFoundError(Exception):
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.strip().upper()
        super().__init__(f"Coin '{self.symbol}' was not found.")


class MarketDataCoinConflictError(Exception):
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.strip().upper()
        super().__init__(f"Coin '{self.symbol}' already exists.")


_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Market data request validation failed.",
    status.HTTP_404_NOT_FOUND: "Requested market-data resource was not found.",
    status.HTTP_409_CONFLICT: "Requested market-data mutation conflicts with existing state.",
}


def market_data_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def market_data_error_to_http(exc: Exception) -> HTTPException | None:
    if isinstance(exc, MarketDataCoinNotFoundError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message=str(exc),
        )
    if isinstance(exc, MarketDataCoinConflictError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="duplicate_request",
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
    "MarketDataCoinConflictError",
    "MarketDataCoinNotFoundError",
    "market_data_error_responses",
    "market_data_error_to_http",
]
