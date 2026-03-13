from __future__ import annotations

from datetime import datetime, timezone
from typing import TypeVar

from fastapi import Response, status

from src.core.http.contracts import AcceptedResponse, CreatedResponse, PageEnvelope

ItemT = TypeVar("ItemT")


def created(item: ItemT) -> CreatedResponse[ItemT]:
    return CreatedResponse(item=item)


def accepted(
    *,
    operation_type: str,
    operation_id: str | None = None,
    deduplicated: bool = False,
    message: str | None = None,
    correlation_id: str | None = None,
) -> AcceptedResponse:
    return AcceptedResponse(
        operation_id=operation_id,
        operation_type=operation_type,
        accepted_at=datetime.now(timezone.utc),
        deduplicated=deduplicated,
        message=message,
        correlation_id=correlation_id,
    )


def no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def page_response(page: PageEnvelope[ItemT]) -> PageEnvelope[ItemT]:
    return page
