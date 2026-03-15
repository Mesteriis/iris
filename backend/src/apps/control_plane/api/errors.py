from __future__ import annotations

from fastapi import HTTPException, status

from src.apps.control_plane.exceptions import (
    EventRouteCompatibilityError,
    EventRouteConflict,
    EventRouteNotFound,
    TopologyDraftConcurrencyConflict,
    TopologyDraftNotFound,
    TopologyDraftStateError,
)
from src.core.errors import (
    ConcurrencyConflictError,
    ControlModeRequiredError,
    ControlTokenInvalidError,
    DuplicateRequestError,
    InvalidAccessModeError,
    InvalidStateTransitionError,
    PolicyDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from src.core.http.errors import ApiError, ApiErrorFactory

_ERROR_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Request validation or control-plane state policy failed.",
    status.HTTP_403_FORBIDDEN: "Control-plane access policy rejected the request.",
    status.HTTP_404_NOT_FOUND: "Requested control-plane resource was not found.",
    status.HTTP_409_CONFLICT: "The requested mutation conflicts with the current control-plane state.",
}


def control_plane_error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        int(status_code): {
            "model": ApiError,
            "description": _ERROR_DESCRIPTIONS[int(status_code)],
        }
        for status_code in status_codes
    }


def invalid_access_mode_error(*, locale: str, value: str | None = None) -> HTTPException:
    return ApiErrorFactory.from_platform_error(
        InvalidAccessModeError(locale=locale),
        details=[
            ApiErrorFactory.build_detail(
                field="X-IRIS-Access-Mode",
                message_key="errors.control_plane.detail.allowed_access_modes",
                locale=locale,
                value={"provided": value, "allowed": ["observe", "control"]},
            )
        ],
    )


def control_mode_required_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ControlModeRequiredError(locale=locale))


def control_token_invalid_error(*, locale: str) -> HTTPException:
    return ApiErrorFactory.from_platform_error(ControlTokenInvalidError(locale=locale))


def event_definition_not_found_error(*, locale: str, event_type: str) -> HTTPException:
    del event_type
    return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="event definition", locale=locale))


def control_plane_error_to_http(exc: Exception, *, locale: str) -> HTTPException | None:
    if isinstance(exc, EventRouteCompatibilityError):
        return ApiErrorFactory.from_platform_error(ValidationFailedError(locale=locale))
    if isinstance(exc, TopologyDraftConcurrencyConflict):
        return ApiErrorFactory.from_platform_error(
            ConcurrencyConflictError(locale=locale),
            details=[
                ApiErrorFactory.build_detail(
                    field="resource_id",
                    message_key="errors.control_plane.detail.draft_id",
                    locale=locale,
                    value=exc.draft_id,
                ),
                ApiErrorFactory.build_detail(
                    field="expected_version",
                    message_key="errors.control_plane.detail.expected_version",
                    locale=locale,
                    value=exc.expected_version,
                ),
                ApiErrorFactory.build_detail(
                    field="current_version",
                    message_key="errors.control_plane.detail.current_version",
                    locale=locale,
                    value=exc.current_version,
                ),
            ],
        )
    if isinstance(exc, TopologyDraftStateError):
        return ApiErrorFactory.from_platform_error(InvalidStateTransitionError(locale=locale))
    if isinstance(exc, EventRouteNotFound):
        return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="event route", locale=locale))
    if isinstance(exc, TopologyDraftNotFound):
        return ApiErrorFactory.from_platform_error(ResourceNotFoundError(resource="topology draft", locale=locale))
    if isinstance(exc, EventRouteConflict):
        return ApiErrorFactory.from_platform_error(DuplicateRequestError(locale=locale))
    return None


__all__ = [
    "control_mode_required_error",
    "control_plane_error_responses",
    "control_plane_error_to_http",
    "control_token_invalid_error",
    "event_definition_not_found_error",
    "invalid_access_mode_error",
]
