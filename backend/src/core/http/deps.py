from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request

from src.core.http.operation_store import OperationStore
from src.core.http.tracing import TraceContext
from src.core.i18n import LocalePolicy, normalize_locale, resolve_locale
from src.core.settings import Settings, get_settings


def get_trace_context(request: Request) -> TraceContext:
    return TraceContext(
        request_id=request.headers.get("X-Request-Id"),
        correlation_id=request.headers.get("X-Correlation-Id"),
        causation_id=request.headers.get("X-Causation-Id"),
    )


def get_operation_store() -> OperationStore:
    return OperationStore()


def build_request_locale_policy(*, settings: Settings | None = None) -> LocalePolicy:
    effective_settings = settings or get_settings()
    default_locale = normalize_locale(getattr(effective_settings.language, "value", effective_settings.language)) or "en"
    return LocalePolicy(
        supported_locales=("en", "ru"),
        default_locale=default_locale,
        fallback_locale="en",
    )


def resolve_request_locale(
    request: Request,
    *,
    language: str | None = None,
    locale: str | None = None,
    settings: Settings | None = None,
) -> str:
    explicit_locale = locale or language or request.headers.get("X-IRIS-Locale")
    resolution = resolve_locale(
        explicit_locale=explicit_locale,
        accept_language=request.headers.get("Accept-Language"),
        policy=build_request_locale_policy(settings=settings),
    )
    return resolution.effective_locale


def get_request_locale(
    request: Request,
    language: str | None = Query(default=None),
    locale: str | None = Query(default=None),
) -> str:
    return resolve_request_locale(request, language=language, locale=locale)


TraceContextDep = Annotated[TraceContext, Depends(get_trace_context)]
OperationStoreDep = Annotated[OperationStore, Depends(get_operation_store)]
RequestLocaleDep = Annotated[str, Depends(get_request_locale)]


__all__ = [
    "OperationStoreDep",
    "RequestLocaleDep",
    "TraceContextDep",
    "build_request_locale_policy",
    "get_operation_store",
    "get_request_locale",
    "get_trace_context",
    "resolve_request_locale",
]
