from __future__ import annotations

from fastapi import HTTPException, status

from src.apps.control_plane.exceptions import (
    EventRouteCompatibilityError,
    EventRouteConflict,
    EventRouteNotFound,
    TopologyDraftNotFound,
    TopologyDraftStateError,
)
from src.core.http.errors import ApiErrorFactory


def invalid_access_mode_error() -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="validation_failed",
        message="X-IRIS-Access-Mode must be 'observe' or 'control'.",
    )


def control_mode_required_error() -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="policy_denied",
        message="Control mode is required for topology mutations.",
    )


def control_token_invalid_error() -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="authorization_denied",
        message="Control token is missing or invalid.",
    )


def event_definition_not_found_error(event_type: str) -> HTTPException:
    return ApiErrorFactory.to_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message=f"Event definition '{event_type}' was not found.",
    )


def control_plane_error_to_http(exc: Exception) -> HTTPException | None:
    if isinstance(exc, EventRouteCompatibilityError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_failed",
            message=str(exc),
        )
    if isinstance(exc, TopologyDraftStateError):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_state_transition",
            message=str(exc),
        )
    if isinstance(exc, (EventRouteNotFound, TopologyDraftNotFound)):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message=str(exc),
        )
    if isinstance(exc, EventRouteConflict):
        return ApiErrorFactory.to_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="duplicate_request",
            message=str(exc),
        )
    return None


__all__ = [
    "control_mode_required_error",
    "control_plane_error_to_http",
    "control_token_invalid_error",
    "event_definition_not_found_error",
    "invalid_access_mode_error",
]
