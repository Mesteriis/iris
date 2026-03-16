from datetime import UTC, datetime
from typing import TypeVar

from fastapi import Response, status

from src.core.http.contracts import AcceptedResponse, CreatedResponse, PageEnvelope

ItemT = TypeVar("ItemT")


def created[ItemT](item: ItemT) -> CreatedResponse[ItemT]:
    return CreatedResponse(item=item)


def accepted(
    *,
    operation_type: str,
    operation_id: str | None = None,
    deduplicated: bool = False,
    message: str | None = None,
    message_key: str | None = None,
    message_params: dict[str, object] | None = None,
    locale: str | None = None,
    correlation_id: str | None = None,
) -> AcceptedResponse:
    return AcceptedResponse(
        operation_id=operation_id,
        operation_type=operation_type,
        accepted_at=datetime.now(UTC),
        deduplicated=deduplicated,
        message=message,
        message_key=message_key,
        message_params=dict(message_params or {}),
        locale=locale,
        correlation_id=correlation_id,
    )


def no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def page_response[ItemT](page: PageEnvelope[ItemT]) -> PageEnvelope[ItemT]:
    return page
