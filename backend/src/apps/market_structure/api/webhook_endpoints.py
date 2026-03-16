from fastapi import APIRouter, status

from src.apps.market_structure.api.contracts import (
    ManualMarketStructureIngestRequest,
    MarketStructureIngestResultRead,
    NativeWebhookPayloadWrite,
)
from src.apps.market_structure.api.deps import MarketStructureCommandDep, MarketStructureIngestAccessDep
from src.apps.market_structure.api.errors import (
    market_structure_error_responses,
    market_structure_error_to_http,
    market_structure_ingest_result_to_http,
)
from src.apps.market_structure.api.presenters import market_structure_ingest_result_read
from src.apps.market_structure.services.results import MarketStructureIngestResult
from src.core.http.command_executor import execute_command
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["market-structure:webhooks"])


@router.post(
    "/sources/{source_id}/snapshots",
    response_model=MarketStructureIngestResultRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest normalized market structure snapshots",
    responses=market_structure_error_responses(400, 401, 404),
)
async def ingest_market_structure_snapshots(
    source_id: int,
    payload: ManualMarketStructureIngestRequest,
    access: MarketStructureIngestAccessDep,
    commands: MarketStructureCommandDep,
    request_locale: RequestLocaleDep,
) -> MarketStructureIngestResultRead:
    async def action() -> MarketStructureIngestResult:
        result = await commands.service.ingest_manual_snapshots(
            source_id=source_id,
            payload=payload,
            ingest_token=access.token,
        )
        http_error = market_structure_ingest_result_to_http(result, source_id=source_id, locale=request_locale)
        if http_error is not None:
            raise http_error
        return result

    return await execute_command(
        action=action,
        uow=commands.uow,
        presenter=market_structure_ingest_result_read,
        translate_error=lambda exc: market_structure_error_to_http(exc, locale=request_locale),
    )


@router.post(
    "/sources/{source_id}/webhook/native",
    response_model=MarketStructureIngestResultRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest provider-native market structure webhook payload",
    responses=market_structure_error_responses(400, 401, 404),
)
async def ingest_market_structure_native_webhook_payload(
    source_id: int,
    payload: NativeWebhookPayloadWrite,
    access: MarketStructureIngestAccessDep,
    commands: MarketStructureCommandDep,
    request_locale: RequestLocaleDep,
) -> MarketStructureIngestResultRead:
    async def action() -> MarketStructureIngestResult:
        result = await commands.service.ingest_native_webhook_payload(
            source_id=source_id,
            payload=dict(payload.root),
            ingest_token=access.token,
        )
        http_error = market_structure_ingest_result_to_http(result, source_id=source_id, locale=request_locale)
        if http_error is not None:
            raise http_error
        return result

    return await execute_command(
        action=action,
        uow=commands.uow,
        presenter=market_structure_ingest_result_read,
        translate_error=lambda exc: market_structure_error_to_http(exc, locale=request_locale),
    )
