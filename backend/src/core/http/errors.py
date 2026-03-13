from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from fastapi import HTTPException
from pydantic import Field

from src.core.http.contracts import HttpContract


class ApiErrorDetail(HttpContract):
    field: str | None = None
    message: str
    value: object | None = None


class ApiError(HttpContract):
    code: str
    message: str
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
    def build(
        *,
        code: str,
        message: str,
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
            details=details,
            retryable=retryable,
            request_id=request_id,
            correlation_id=correlation_id,
            docs_ref=docs_ref,
            operation_id=operation_id,
        )
        return HTTPException(status_code=status_code, detail=payload.model_dump(mode="json"), headers=dict(headers or {}))
