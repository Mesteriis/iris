from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from src.apps.market_structure.exceptions import (
    InvalidMarketStructureSourceConfigurationError,
    InvalidMarketStructureWebhookPayloadError,
    UnsupportedMarketStructurePluginError,
    UnauthorizedMarketStructureIngestError,
)
from src.apps.market_structure.query_services import MarketStructureQueryService
from src.apps.market_structure.schemas import (
    BinanceMarketStructureSourceCreateRequest,
    BybitMarketStructureSourceCreateRequest,
    ManualMarketStructureIngestRequest,
    ManualWebhookMarketStructureSourceCreateRequest,
    ManualPushMarketStructureSourceCreateRequest,
    MarketStructureOnboardingRead,
    MarketStructurePluginRead,
    MarketStructureSnapshotRead,
    MarketStructureSourceCreate,
    MarketStructureSourceHealthRead,
    MarketStructureSourceRead,
    MarketStructureSourceUpdate,
    MarketStructureWebhookRegistrationRead,
)
from src.apps.market_structure.services import MarketStructureService, MarketStructureSourceProvisioningService
from src.core.db.persistence import thaw_json_value
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

router = APIRouter(tags=["market-structure"])
DB_UOW = Depends(get_uow)


def _snapshot_schema_from_read_model(item) -> MarketStructureSnapshotRead:
    return MarketStructureSnapshotRead.model_validate(
        {
            "id": item.id,
            "coin_id": item.coin_id,
            "symbol": item.symbol,
            "timeframe": item.timeframe,
            "venue": item.venue,
            "timestamp": item.timestamp,
            "last_price": item.last_price,
            "mark_price": item.mark_price,
            "index_price": item.index_price,
            "funding_rate": item.funding_rate,
            "open_interest": item.open_interest,
            "basis": item.basis,
            "liquidations_long": item.liquidations_long,
            "liquidations_short": item.liquidations_short,
            "volume": item.volume,
            "payload_json": thaw_json_value(item.payload_json),
        }
    )


@router.get("/market-structure/plugins", response_model=list[MarketStructurePluginRead])
async def read_market_structure_plugins(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[MarketStructurePluginRead]:
    items = await MarketStructureQueryService(uow.session).list_plugins()
    return [MarketStructurePluginRead.model_validate(item) for item in items]


@router.get("/market-structure/onboarding/wizard", response_model=MarketStructureOnboardingRead)
async def read_market_structure_onboarding_wizard() -> MarketStructureOnboardingRead:
    return MarketStructureSourceProvisioningService.wizard_spec()


@router.get("/market-structure/sources", response_model=list[MarketStructureSourceRead])
async def read_market_structure_sources(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[MarketStructureSourceRead]:
    items = await MarketStructureQueryService(uow.session).list_sources()
    return [MarketStructureSourceRead.model_validate(item) for item in items]


@router.get("/market-structure/sources/{source_id}/health", response_model=MarketStructureSourceHealthRead)
async def read_market_structure_source_health(
    source_id: int,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureSourceHealthRead:
    health = await MarketStructureQueryService(uow.session).get_source_health_read_by_id(source_id)
    if health is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market structure source '{source_id}' was not found.",
        )
    return MarketStructureSourceHealthRead.model_validate(health)


@router.post("/market-structure/sources", response_model=MarketStructureSourceRead, status_code=status.HTTP_201_CREATED)
async def create_market_structure_source(
    payload: MarketStructureSourceCreate,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureSourceRead:
    try:
        return await MarketStructureService(uow).create_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/binance-usdm",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_binance_market_structure_source(
    payload: BinanceMarketStructureSourceCreateRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureSourceRead:
    try:
        return await MarketStructureSourceProvisioningService(uow).create_binance_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/bybit-derivatives",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_bybit_market_structure_source(
    payload: BybitMarketStructureSourceCreateRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureSourceRead:
    try:
        return await MarketStructureSourceProvisioningService(uow).create_bybit_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/manual-push",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_market_structure_source(
    payload: ManualPushMarketStructureSourceCreateRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureSourceRead:
    try:
        return await MarketStructureSourceProvisioningService(uow).create_manual_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/liqscope-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_liqscope_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(uow).create_liqscope_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/liquidation-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_liquidation_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(uow).create_liquidation_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/derivatives-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_derivatives_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(uow).create_derivatives_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/coinglass-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_coinglass_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(uow).create_coinglass_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/hyblock-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_hyblock_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(uow).create_hyblock_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/coinalyze-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_coinalyze_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(uow).create_coinalyze_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/market-structure/sources/{source_id}", response_model=MarketStructureSourceRead)
async def patch_market_structure_source(
    source_id: int,
    payload: MarketStructureSourceUpdate,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureSourceRead:
    try:
        updated = await MarketStructureService(uow).update_source(source_id, payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market structure source '{source_id}' was not found.",
        )
    return updated


@router.delete("/market-structure/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_market_structure_source(source_id: int, uow: BaseAsyncUnitOfWork = DB_UOW) -> None:
    deleted = await MarketStructureService(uow).delete_source(source_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market structure source '{source_id}' was not found.",
        )


@router.get("/market-structure/sources/{source_id}/webhook", response_model=MarketStructureWebhookRegistrationRead)
async def read_market_structure_source_webhook(
    source_id: int,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureWebhookRegistrationRead:
    try:
        registration = await MarketStructureSourceProvisioningService(uow).read_webhook_registration(
            source_id,
            include_token=False,
        )
    except InvalidMarketStructureSourceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if registration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market structure source '{source_id}' was not found.",
        )
    return registration


@router.post(
    "/market-structure/sources/{source_id}/webhook/rotate-token",
    response_model=MarketStructureWebhookRegistrationRead,
)
async def rotate_market_structure_source_webhook_token(
    source_id: int,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketStructureWebhookRegistrationRead:
    try:
        registration = await MarketStructureSourceProvisioningService(uow).rotate_webhook_token(source_id)
    except InvalidMarketStructureSourceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if registration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market structure source '{source_id}' was not found.",
        )
    return registration


@router.get("/market-structure/snapshots", response_model=list[MarketStructureSnapshotRead])
async def read_market_structure_snapshots(
    coin_symbol: str | None = Query(default=None),
    venue: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[MarketStructureSnapshotRead]:
    items = await MarketStructureQueryService(uow.session).list_snapshots(
        coin_symbol=coin_symbol, venue=venue, limit=limit
    )
    return [_snapshot_schema_from_read_model(item) for item in items]


@router.post("/market-structure/sources/{source_id}/jobs/run", status_code=status.HTTP_202_ACCEPTED)
async def run_market_structure_source_job(
    source_id: int,
    limit: int = Query(default=1, ge=1, le=10),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> dict[str, object]:
    from src.apps.market_structure.tasks import poll_market_structure_source_job

    source = await MarketStructureQueryService(uow.session).get_source_read_by_id(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market structure source '{source_id}' was not found.",
        )

    await poll_market_structure_source_job.kiq(source_id=int(source_id), limit=int(limit))
    return {
        "status": "queued",
        "source_id": int(source_id),
        "limit": int(limit),
    }


@router.post("/market-structure/health/jobs/run", status_code=status.HTTP_202_ACCEPTED)
async def run_market_structure_health_job() -> dict[str, object]:
    from src.apps.market_structure.tasks import refresh_market_structure_source_health_job

    await refresh_market_structure_source_health_job.kiq()
    return {"status": "queued"}


@router.post("/market-structure/sources/{source_id}/snapshots", status_code=status.HTTP_202_ACCEPTED)
async def ingest_market_structure_snapshots(
    source_id: int,
    payload: ManualMarketStructureIngestRequest,
    token: str | None = Query(default=None),
    x_iris_ingest_token: str | None = Header(default=None, alias="X-IRIS-Ingest-Token"),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> dict[str, object]:
    try:
        result = await MarketStructureService(uow).ingest_manual_snapshots(
            source_id=source_id,
            payload=payload,
            ingest_token=x_iris_ingest_token or token,
        )
    except UnauthorizedMarketStructureIngestError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if result["status"] == "error":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Market structure source '{source_id}' was not found."
        )
    if result["status"] == "skipped":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(result["reason"]))
    return result


@router.post("/market-structure/sources/{source_id}/webhook/native", status_code=status.HTTP_202_ACCEPTED)
async def ingest_market_structure_native_webhook_payload(
    source_id: int,
    payload: dict[str, object],
    token: str | None = Query(default=None),
    x_iris_ingest_token: str | None = Header(default=None, alias="X-IRIS-Ingest-Token"),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> dict[str, object]:
    try:
        result = await MarketStructureService(uow).ingest_native_webhook_payload(
            source_id=source_id,
            payload=dict(payload),
            ingest_token=x_iris_ingest_token or token,
        )
    except UnauthorizedMarketStructureIngestError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except (InvalidMarketStructureSourceConfigurationError, InvalidMarketStructureWebhookPayloadError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result["status"] == "error":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Market structure source '{source_id}' was not found."
        )
    if result["status"] == "skipped":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(result["reason"]))
    return result
