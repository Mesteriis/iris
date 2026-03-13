from __future__ import annotations

from fastapi import APIRouter, status

from src.apps.market_structure.api.contracts import (
    MarketStructureSourceCreate,
    MarketStructureSourceRead,
    MarketStructureSourceUpdate,
    MarketStructureWebhookRegistrationRead,
)
from src.apps.market_structure.api.deps import MarketStructureCommandDep, MarketStructureProvisioningDep
from src.apps.market_structure.api.errors import (
    MarketStructureSourceNotFoundError,
    market_structure_error_responses,
    market_structure_error_to_http,
)
from src.apps.market_structure.api.presenters import (
    market_structure_source_read,
    market_structure_webhook_registration_read,
)
from src.core.http.command_executor import execute_command, execute_command_no_content

router = APIRouter(tags=["market-structure:commands"])


@router.post(
    "/sources",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a market structure source",
    responses=market_structure_error_responses(400),
)
async def create_market_structure_source(
    payload: MarketStructureSourceCreate,
    commands: MarketStructureCommandDep,
) -> MarketStructureSourceRead:
    return await execute_command(
        action=lambda: commands.service.create_source(payload),
        uow=commands.uow,
        presenter=market_structure_source_read,
        translate_error=market_structure_error_to_http,
    )


@router.patch(
    "/sources/{source_id}",
    response_model=MarketStructureSourceRead,
    summary="Update a market structure source",
    responses=market_structure_error_responses(400, 404),
)
async def patch_market_structure_source(
    source_id: int,
    payload: MarketStructureSourceUpdate,
    commands: MarketStructureCommandDep,
) -> MarketStructureSourceRead:
    async def action() -> MarketStructureSourceRead:
        updated = await commands.service.update_source(source_id, payload)
        if updated is None:
            raise MarketStructureSourceNotFoundError(source_id)
        return updated

    return await execute_command(
        action=action,
        uow=commands.uow,
        presenter=market_structure_source_read,
        translate_error=market_structure_error_to_http,
    )


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a market structure source",
    responses=market_structure_error_responses(404),
)
async def delete_market_structure_source(
    source_id: int,
    commands: MarketStructureCommandDep,
) -> None:
    async def action() -> object:
        deleted = await commands.service.delete_source(source_id)
        if not deleted:
            raise MarketStructureSourceNotFoundError(source_id)
        return {"deleted": True}

    await execute_command_no_content(
        action=action,
        uow=commands.uow,
        translate_error=market_structure_error_to_http,
    )


@router.post(
    "/sources/{source_id}/webhook/rotate-token",
    response_model=MarketStructureWebhookRegistrationRead,
    summary="Rotate a market structure source webhook token",
    responses=market_structure_error_responses(400, 404),
)
async def rotate_market_structure_source_webhook_token(
    source_id: int,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureWebhookRegistrationRead:
    async def action() -> MarketStructureWebhookRegistrationRead:
        registration = await provisioning.service.rotate_webhook_token(source_id)
        if registration is None:
            raise MarketStructureSourceNotFoundError(source_id)
        return registration

    return await execute_command(
        action=action,
        uow=provisioning.uow,
        presenter=market_structure_webhook_registration_read,
        translate_error=market_structure_error_to_http,
    )
