from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from src.core.http.operation_store import OperationStore
from src.core.http.tracing import TraceContext


def get_trace_context(request: Request) -> TraceContext:
    return TraceContext(
        request_id=request.headers.get("X-Request-Id"),
        correlation_id=request.headers.get("X-Correlation-Id"),
        causation_id=request.headers.get("X-Causation-Id"),
    )


def get_operation_store() -> OperationStore:
    return OperationStore()


TraceContextDep = Annotated[TraceContext, Depends(get_trace_context)]
OperationStoreDep = Annotated[OperationStore, Depends(get_operation_store)]


__all__ = [
    "OperationStoreDep",
    "TraceContextDep",
    "get_operation_store",
    "get_trace_context",
]
