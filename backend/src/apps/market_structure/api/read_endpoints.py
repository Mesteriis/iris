from fastapi import APIRouter, Query

from src.apps.market_structure.api.contracts import (
    MarketStructurePluginRead,
    MarketStructureSnapshotRead,
    MarketStructureSourceHealthRead,
    MarketStructureSourceRead,
    MarketStructureWebhookRegistrationRead,
)
from src.apps.market_structure.api.deps import MarketStructureProvisioningDep, MarketStructureQueryDep
from src.apps.market_structure.api.errors import (
    market_structure_error_responses,
    market_structure_error_to_http,
    market_structure_source_not_found_error,
)
from src.apps.market_structure.api.presenters import (
    market_structure_plugin_read,
    market_structure_snapshot_read,
    market_structure_source_health_read,
    market_structure_source_read,
    market_structure_webhook_registration_read,
)
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["market-structure:read"])


@router.get(
    "/plugins",
    response_model=list[MarketStructurePluginRead],
    summary="List market structure plugins",
)
async def read_market_structure_plugins(service: MarketStructureQueryDep) -> list[MarketStructurePluginRead]:
    return [market_structure_plugin_read(item) for item in await service.list_plugins()]


@router.get(
    "/sources",
    response_model=list[MarketStructureSourceRead],
    summary="List market structure sources",
)
async def read_market_structure_sources(service: MarketStructureQueryDep) -> list[MarketStructureSourceRead]:
    return [market_structure_source_read(item) for item in await service.list_sources()]


@router.get(
    "/sources/{source_id}/health",
    response_model=MarketStructureSourceHealthRead,
    summary="Read market structure source health",
    responses=market_structure_error_responses(404),
)
async def read_market_structure_source_health(
    source_id: int,
    service: MarketStructureQueryDep,
    request_locale: RequestLocaleDep,
) -> MarketStructureSourceHealthRead:
    health = await service.get_source_health_read_by_id(source_id)
    if health is None:
        raise market_structure_source_not_found_error(locale=request_locale)
    return market_structure_source_health_read(health)


@router.get(
    "/sources/{source_id}/webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    summary="Read market structure webhook registration",
    responses=market_structure_error_responses(400, 404),
)
async def read_market_structure_source_webhook(
    source_id: int,
    provisioning: MarketStructureProvisioningDep,
    request_locale: RequestLocaleDep,
) -> MarketStructureWebhookRegistrationRead:
    try:
        registration = await provisioning.service.read_webhook_registration(source_id, include_token=False)
    except Exception as exc:
        http_error = market_structure_error_to_http(exc, locale=request_locale)
        if http_error is not None:
            raise http_error from exc
        raise
    if registration is None:
        raise market_structure_source_not_found_error(locale=request_locale)
    return market_structure_webhook_registration_read(registration)


@router.get(
    "/snapshots",
    response_model=list[MarketStructureSnapshotRead],
    summary="List market structure snapshots",
)
async def read_market_structure_snapshots(
    service: MarketStructureQueryDep,
    coin_symbol: str | None = Query(default=None),
    venue: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[MarketStructureSnapshotRead]:
    items = await service.list_snapshots(coin_symbol=coin_symbol, venue=venue, limit=limit)
    return [market_structure_snapshot_read(item) for item in items]
