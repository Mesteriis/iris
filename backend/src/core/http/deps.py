from typing import Annotated

from fastapi import Depends, Request

from src.core.http.operation_store import OperationStore
from src.core.http.tracing import TraceContext
from src.core.i18n import LocalePolicy, build_locale_policy
from src.core.settings import Settings


def get_trace_context(request: Request) -> TraceContext:
    return TraceContext(
        request_id=request.headers.get("X-Request-Id"),
        correlation_id=request.headers.get("X-Correlation-Id"),
        causation_id=request.headers.get("X-Causation-Id"),
    )


def get_operation_store() -> OperationStore:
    return OperationStore()


def build_request_locale_policy(*, settings: Settings | None = None) -> LocalePolicy:
    return build_locale_policy(settings=settings)


def resolve_request_locale(
    request: Request | None = None,
    *,
    language: str | None = None,
    locale: str | None = None,
    settings: Settings | None = None,
) -> str:
    del request, language, locale
    return build_request_locale_policy(settings=settings).default_locale


def get_request_locale() -> str:
    return resolve_request_locale()


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
