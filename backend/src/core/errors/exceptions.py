from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.core.errors.catalog import PLATFORM_ERROR_REGISTRY
from src.core.errors.registry import ErrorDefinition
from src.core.i18n import TranslationService, get_translation_service


class PlatformError(Exception):
    def __init__(
        self,
        definition: ErrorDefinition,
        *,
        params: Mapping[str, object] | None = None,
        details: Mapping[str, Any] | None = None,
        locale: str | None = None,
        translator: TranslationService | None = None,
        retryable: bool | None = None,
    ) -> None:
        localized = (translator or get_translation_service()).translate(
            definition.message_key,
            locale=locale,
            params=params,
        )
        self.definition = definition
        self.params = dict(params or {})
        self.details = dict(details or {})
        self.locale = localized.locale
        self.code = definition.error_code
        self.message_key = definition.message_key
        self.message = localized.text
        self.http_status = definition.http_status
        self.domain = definition.domain
        self.category = definition.category
        self.severity = definition.severity
        self.retryable = definition.retryable if retryable is None else retryable
        self.safe_to_expose = definition.safe_to_expose
        super().__init__(self.message)

    def to_metadata(self) -> dict[str, object]:
        return {
            "error_code": self.code,
            "message_key": self.message_key,
            "domain": self.domain.value,
            "category": self.category.value,
            "http_status": self.http_status,
            "severity": self.severity.value,
            "retryable": self.retryable,
            "safe_to_expose": self.safe_to_expose,
            "params": dict(self.params),
            "details": dict(self.details),
            "locale": self.locale,
        }


class RegistryBackedPlatformError(PlatformError):
    error_code: str

    def __init__(
        self,
        *,
        details: Mapping[str, Any] | None = None,
        params: Mapping[str, object] | None = None,
        locale: str | None = None,
        translator: TranslationService | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(
            PLATFORM_ERROR_REGISTRY.get(self.error_code),
            details=details,
            params=params,
            locale=locale,
            translator=translator,
            retryable=retryable,
        )


class ValidationFailedError(RegistryBackedPlatformError):
    error_code = "validation_failed"

    def __init__(
        self,
        *,
        details: Mapping[str, Any] | None = None,
        params: Mapping[str, object] | None = None,
        locale: str | None = None,
        translator: TranslationService | None = None,
    ) -> None:
        super().__init__(details=details, params=params, locale=locale, translator=translator)


class ResourceNotFoundError(RegistryBackedPlatformError):
    error_code = "resource_not_found"

    def __init__(
        self,
        *,
        resource: str,
        details: Mapping[str, Any] | None = None,
        locale: str | None = None,
        translator: TranslationService | None = None,
    ) -> None:
        super().__init__(details=details, params={"resource": resource}, locale=locale, translator=translator)


class DuplicateRequestError(RegistryBackedPlatformError):
    error_code = "duplicate_request"


class InvalidStateTransitionError(RegistryBackedPlatformError):
    error_code = "invalid_state_transition"


class AuthenticationFailedError(RegistryBackedPlatformError):
    error_code = "authentication_failed"


class AuthorizationDeniedError(RegistryBackedPlatformError):
    error_code = "authorization_denied"


class PolicyDeniedError(RegistryBackedPlatformError):
    error_code = "policy_denied"


class ConcurrencyConflictError(RegistryBackedPlatformError):
    error_code = "concurrency_conflict"


class IntegrationUnreachableError(RegistryBackedPlatformError):
    error_code = "integration_unreachable"


class PromptVeilLockedPlatformError(RegistryBackedPlatformError):
    error_code = "prompt_veil_locked"


class InvalidAccessModeError(RegistryBackedPlatformError):
    error_code = "invalid_access_mode"


class ControlModeRequiredError(RegistryBackedPlatformError):
    error_code = "control_mode_required"


class ControlTokenInvalidError(RegistryBackedPlatformError):
    error_code = "control_token_invalid"
