from fastapi import HTTPException, status

from src.core.errors import DuplicateRequestError, ResourceNotFoundError, ValidationFailedError
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


def market_data_coin_not_found_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="coin", locale=locale))


def market_data_error_to_http(exc: Exception, *, locale: str) -> HTTPException | None:
    if isinstance(exc, MarketDataCoinNotFoundError):
        return market_data_coin_not_found_error(locale=locale)
    if isinstance(exc, MarketDataCoinConflictError):
        return ApiErrorFactory.from_platform_error(DuplicateRequestError(locale=locale))
    if isinstance(exc, ValueError):
        return ApiErrorFactory.from_platform_error(ValidationFailedError(locale=locale))
    return None


__all__ = [
    "MarketDataCoinConflictError",
    "MarketDataCoinNotFoundError",
    "market_data_coin_not_found_error",
    "market_data_error_responses",
    "market_data_error_to_http",
]
