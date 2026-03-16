# ruff: noqa: RUF001


import pytest
from src.core.errors import (
    DuplicateErrorCodeError,
    DuplicateMessageKeyError,
    ErrorCategory,
    ErrorDefinition,
    ErrorDomain,
    ErrorRegistry,
    ErrorSeverity,
    ResourceNotFoundError,
)
from src.core.http.errors import ApiErrorFactory


def test_error_registry_rejects_duplicate_codes_and_message_keys() -> None:
    registry = ErrorRegistry(
        definitions=(
            ErrorDefinition(
                error_code="duplicate_test",
                message_key="error.test.duplicate",
                domain=ErrorDomain.CORE,
                category=ErrorCategory.INTERNAL,
                http_status=500,
                severity=ErrorSeverity.ERROR,
            ),
        )
    )

    with pytest.raises(DuplicateErrorCodeError):
        registry.register(
            ErrorDefinition(
                error_code="duplicate_test",
                message_key="error.test.other",
                domain=ErrorDomain.CORE,
                category=ErrorCategory.INTERNAL,
                http_status=500,
                severity=ErrorSeverity.ERROR,
            )
        )

    with pytest.raises(DuplicateMessageKeyError):
        registry.register(
            ErrorDefinition(
                error_code="other_code",
                message_key="error.test.duplicate",
                domain=ErrorDomain.CORE,
                category=ErrorCategory.INTERNAL,
                http_status=500,
                severity=ErrorSeverity.ERROR,
            )
        )


def test_platform_error_keeps_structured_metadata_without_localizing_message() -> None:
    error = ResourceNotFoundError(resource="signal", locale="ru")

    assert error.code == "resource_not_found"
    assert error.message_key == "error.resource.not_found"
    assert error.message == "resource_not_found (resource='signal')"
    assert error.to_metadata()["locale"] == "ru"
    assert error.to_metadata()["http_status"] == 404


def test_api_error_factory_adapts_platform_error_without_changing_wire_shape() -> None:
    error = ResourceNotFoundError(resource="signal")

    payload = ApiErrorFactory.build_from_platform_error(error, locale="en")
    http_error = ApiErrorFactory.from_platform_error(error, locale="en")

    assert payload.code == "resource_not_found"
    assert payload.message == "The requested signal was not found."
    assert http_error.status_code == 404
    assert http_error.detail["code"] == "resource_not_found"
    assert http_error.detail["message"] == "The requested signal was not found."
