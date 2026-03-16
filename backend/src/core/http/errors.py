from collections.abc import Mapping
from typing import Protocol

from fastapi import HTTPException
from pydantic import Field

from src.core.errors import PlatformError
from src.core.http.contracts import HttpContract
from src.core.i18n import get_translation_service


class ApiErrorDetail(HttpContract):
    field: str | None = None
    message: str
    message_key: str | None = None
    message_params: dict[str, object] = Field(default_factory=dict)
    locale: str | None = None
    value: object | None = None


class ApiError(HttpContract):
    code: str
    message: str
    message_key: str | None = None
    message_params: dict[str, object] = Field(default_factory=dict)
    locale: str | None = None
    domain: str | None = None
    category: str | None = None
    http_status: int | None = None
    severity: str | None = None
    safe_to_expose: bool | None = None
    details: list[ApiErrorDetail] = Field(default_factory=list)
    retryable: bool = False
    request_id: str | None = None
    correlation_id: str | None = None
    docs_ref: str | None = None
    operation_id: str | None = None


class DomainHttpErrorTranslator(Protocol):
    def __call__(self, exc: Exception) -> HTTPException | None: ...


class ApiErrorFactory:
    @staticmethod
    def build_detail(
        *,
        field: str | None = None,
        message_key: str,
        message_params: dict[str, object] | None = None,
        locale: str | None = None,
        value: object | None = None,
    ) -> ApiErrorDetail:
        localized = get_translation_service().translate(message_key, locale=locale, params=message_params)
        return ApiErrorDetail(
            field=field,
            message=localized.text,
            message_key=message_key,
            message_params=dict(message_params or {}),
            locale=localized.locale,
            value=value,
        )

    @staticmethod
    def build(
        *,
        code: str,
        message: str,
        message_key: str | None = None,
        message_params: dict[str, object] | None = None,
        locale: str | None = None,
        domain: str | None = None,
        category: str | None = None,
        http_status: int | None = None,
        severity: str | None = None,
        safe_to_expose: bool | None = None,
        details: list[ApiErrorDetail] | None = None,
        retryable: bool = False,
        request_id: str | None = None,
        correlation_id: str | None = None,
        docs_ref: str | None = None,
        operation_id: str | None = None,
    ) -> ApiError:
        return ApiError(
            code=code,
            message=message,
            message_key=message_key,
            message_params=dict(message_params or {}),
            locale=locale,
            domain=domain,
            category=category,
            http_status=http_status,
            severity=severity,
            safe_to_expose=safe_to_expose,
            details=list(details or []),
            retryable=retryable,
            request_id=request_id,
            correlation_id=correlation_id,
            docs_ref=docs_ref,
            operation_id=operation_id,
        )

    @staticmethod
    def to_http_exception(
        *,
        status_code: int,
        code: str,
        message: str,
        message_key: str | None = None,
        message_params: dict[str, object] | None = None,
        locale: str | None = None,
        domain: str | None = None,
        category: str | None = None,
        severity: str | None = None,
        safe_to_expose: bool | None = None,
        details: list[ApiErrorDetail] | None = None,
        retryable: bool = False,
        request_id: str | None = None,
        correlation_id: str | None = None,
        docs_ref: str | None = None,
        operation_id: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HTTPException:
        payload = ApiErrorFactory.build(
            code=code,
            message=message,
            message_key=message_key,
            message_params=message_params,
            locale=locale,
            domain=domain,
            category=category,
            http_status=status_code,
            severity=severity,
            safe_to_expose=safe_to_expose,
            details=details,
            retryable=retryable,
            request_id=request_id,
            correlation_id=correlation_id,
            docs_ref=docs_ref,
            operation_id=operation_id,
        )
        return HTTPException(status_code=status_code, detail=payload.model_dump(mode="json"), headers=dict(headers or {}))

    @staticmethod
    def build_from_platform_error(
        exc: PlatformError,
        *,
        locale: str | None = None,
        details: list[ApiErrorDetail] | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        docs_ref: str | None = None,
        operation_id: str | None = None,
    ) -> ApiError:
        localized = get_translation_service().translate(
            exc.message_key,
            locale=locale or exc.locale,
            params=exc.params,
        )
        return ApiErrorFactory.build(
            code=exc.code,
            message=localized.text,
            message_key=exc.message_key,
            message_params=dict(exc.params),
            locale=localized.locale,
            domain=exc.domain.value,
            category=exc.category.value,
            http_status=exc.http_status,
            severity=exc.severity.value,
            safe_to_expose=exc.safe_to_expose,
            details=details,
            retryable=exc.retryable,
            request_id=request_id,
            correlation_id=correlation_id,
            docs_ref=docs_ref,
            operation_id=operation_id,
        )

    @staticmethod
    def from_platform_error(
        exc: PlatformError,
        *,
        locale: str | None = None,
        details: list[ApiErrorDetail] | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        docs_ref: str | None = None,
        operation_id: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HTTPException:
        payload = ApiErrorFactory.build_from_platform_error(
            exc,
            locale=locale,
            details=details,
            request_id=request_id,
            correlation_id=correlation_id,
            docs_ref=docs_ref,
            operation_id=operation_id,
        )
        return HTTPException(
            status_code=exc.http_status,
            detail=payload.model_dump(mode="json"),
            headers=dict(headers or {}),
        )
