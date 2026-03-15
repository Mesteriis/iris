from __future__ import annotations

from fastapi import APIRouter

from src.apps.system.api.contracts import OperationEventResponse, OperationResultResponse, OperationStatusResponse
from src.apps.system.api.deps import SystemOperationFacadeDep
from src.apps.system.api.errors import operation_not_found_error, system_error_responses
from src.apps.system.api.presenters import operation_event_read, operation_result_read, operation_status_read
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["system:operations"])


@router.get(
    "/operations/{operation_id}",
    response_model=OperationStatusResponse,
    summary="Read async operation status",
    responses=system_error_responses(404),
)
async def read_operation_status(
    operation_id: str,
    facade: SystemOperationFacadeDep,
    request_locale: RequestLocaleDep,
) -> OperationStatusResponse:
    status_row = await facade.get_status(operation_id)
    if status_row is None:
        raise operation_not_found_error(operation_id, locale=request_locale)
    return operation_status_read(status_row)


@router.get(
    "/operations/{operation_id}/result",
    response_model=OperationResultResponse,
    summary="Read async operation result",
    responses=system_error_responses(404),
)
async def read_operation_result(
    operation_id: str,
    facade: SystemOperationFacadeDep,
    request_locale: RequestLocaleDep,
) -> OperationResultResponse:
    result = await facade.get_result(operation_id)
    if result is None:
        raise operation_not_found_error(operation_id, locale=request_locale)
    return operation_result_read(result)


@router.get(
    "/operations/{operation_id}/events",
    response_model=list[OperationEventResponse],
    summary="Read async operation events",
    responses=system_error_responses(404),
)
async def list_operation_events(
    operation_id: str,
    facade: SystemOperationFacadeDep,
    request_locale: RequestLocaleDep,
) -> list[OperationEventResponse]:
    status_row = await facade.get_status(operation_id)
    if status_row is None:
        raise operation_not_found_error(operation_id, locale=request_locale)
    return [operation_event_read(item) for item in await facade.list_events(operation_id)]


__all__ = [
    "list_operation_events",
    "read_operation_result",
    "read_operation_status",
    "router",
]
