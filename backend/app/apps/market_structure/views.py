from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.market_structure.exceptions import (
    InvalidMarketStructureSourceConfigurationError,
    InvalidMarketStructureWebhookPayloadError,
    UnsupportedMarketStructurePluginError,
    UnauthorizedMarketStructureIngestError,
)
from app.apps.market_structure.schemas import (
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
from app.apps.market_structure.services import MarketStructureService, MarketStructureSourceProvisioningService
from app.core.db.session import get_db

router = APIRouter(tags=["market-structure"])


@router.get("/market-structure/plugins", response_model=list[MarketStructurePluginRead])
async def read_market_structure_plugins(db: AsyncSession = Depends(get_db)) -> list[MarketStructurePluginRead]:
    return await MarketStructureService(db).list_plugins()


@router.get("/market-structure/onboarding/wizard", response_model=MarketStructureOnboardingRead)
async def read_market_structure_onboarding_wizard() -> MarketStructureOnboardingRead:
    return MarketStructureSourceProvisioningService.wizard_spec()


@router.get("/market-structure/sources", response_model=list[MarketStructureSourceRead])
async def read_market_structure_sources(db: AsyncSession = Depends(get_db)) -> list[MarketStructureSourceRead]:
    return await MarketStructureService(db).list_sources()


@router.get("/market-structure/sources/{source_id}/health", response_model=MarketStructureSourceHealthRead)
async def read_market_structure_source_health(
    source_id: int,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureSourceHealthRead:
    health = await MarketStructureService(db).read_source_health(source_id)
    if health is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market structure source '{source_id}' was not found.",
        )
    return health


@router.post("/market-structure/sources", response_model=MarketStructureSourceRead, status_code=status.HTTP_201_CREATED)
async def create_market_structure_source(
    payload: MarketStructureSourceCreate,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureSourceRead:
    try:
        return await MarketStructureService(db).create_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/binance-usdm",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_binance_market_structure_source(
    payload: BinanceMarketStructureSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureSourceRead:
    try:
        return await MarketStructureSourceProvisioningService(db).create_binance_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/bybit-derivatives",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_bybit_market_structure_source(
    payload: BybitMarketStructureSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureSourceRead:
    try:
        return await MarketStructureSourceProvisioningService(db).create_bybit_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/manual-push",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_market_structure_source(
    payload: ManualPushMarketStructureSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureSourceRead:
    try:
        return await MarketStructureSourceProvisioningService(db).create_manual_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/liqscope-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_liqscope_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(db).create_liqscope_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/liquidation-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_liquidation_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(db).create_liquidation_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/derivatives-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_derivatives_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(db).create_derivatives_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/coinglass-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_coinglass_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(db).create_coinglass_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/hyblock-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_hyblock_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(db).create_hyblock_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/market-structure/onboarding/sources/coinalyze-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_coinalyze_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureWebhookRegistrationRead:
    try:
        return await MarketStructureSourceProvisioningService(db).create_coinalyze_webhook_source(payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/market-structure/sources/{source_id}", response_model=MarketStructureSourceRead)
async def patch_market_structure_source(
    source_id: int,
    payload: MarketStructureSourceUpdate,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureSourceRead:
    try:
        updated = await MarketStructureService(db).update_source(source_id, payload)
    except (InvalidMarketStructureSourceConfigurationError, UnsupportedMarketStructurePluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market structure source '{source_id}' was not found.",
        )
    return updated


@router.delete("/market-structure/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_market_structure_source(source_id: int, db: AsyncSession = Depends(get_db)) -> None:
    deleted = await MarketStructureService(db).delete_source(source_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market structure source '{source_id}' was not found.",
        )


@router.get("/market-structure/sources/{source_id}/webhook", response_model=MarketStructureWebhookRegistrationRead)
async def read_market_structure_source_webhook(
    source_id: int,
    db: AsyncSession = Depends(get_db),
) -> MarketStructureWebhookRegistrationRead:
    try:
        registration = await MarketStructureSourceProvisioningService(db).read_webhook_registration(
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
    db: AsyncSession = Depends(get_db),
) -> MarketStructureWebhookRegistrationRead:
    try:
        registration = await MarketStructureSourceProvisioningService(db).rotate_webhook_token(source_id)
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
    db: AsyncSession = Depends(get_db),
) -> list[MarketStructureSnapshotRead]:
    return await MarketStructureService(db).list_snapshots(coin_symbol=coin_symbol, venue=venue, limit=limit)


@router.post("/market-structure/sources/{source_id}/jobs/run", status_code=status.HTTP_202_ACCEPTED)
async def run_market_structure_source_job(
    source_id: int,
    limit: int = Query(default=1, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    from app.apps.market_structure.tasks import poll_market_structure_source_job

    source = await MarketStructureService(db).get_source(source_id)
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
    from app.apps.market_structure.tasks import refresh_market_structure_source_health_job

    await refresh_market_structure_source_health_job.kiq()
    return {"status": "queued"}


@router.post("/market-structure/sources/{source_id}/snapshots", status_code=status.HTTP_202_ACCEPTED)
async def ingest_market_structure_snapshots(
    source_id: int,
    payload: ManualMarketStructureIngestRequest,
    token: str | None = Query(default=None),
    x_iris_ingest_token: str | None = Header(default=None, alias="X-IRIS-Ingest-Token"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    try:
        result = await MarketStructureService(db).ingest_manual_snapshots(
            source_id=source_id,
            payload=payload,
            ingest_token=x_iris_ingest_token or token,
        )
    except UnauthorizedMarketStructureIngestError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if result["status"] == "error":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Market structure source '{source_id}' was not found.")
    if result["status"] == "skipped":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(result["reason"]))
    return result


@router.post("/market-structure/sources/{source_id}/webhook/native", status_code=status.HTTP_202_ACCEPTED)
async def ingest_market_structure_native_webhook_payload(
    source_id: int,
    payload: dict[str, object],
    token: str | None = Query(default=None),
    x_iris_ingest_token: str | None = Header(default=None, alias="X-IRIS-Ingest-Token"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    try:
        result = await MarketStructureService(db).ingest_native_webhook_payload(
            source_id=source_id,
            payload=dict(payload),
            ingest_token=x_iris_ingest_token or token,
        )
    except UnauthorizedMarketStructureIngestError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except (InvalidMarketStructureSourceConfigurationError, InvalidMarketStructureWebhookPayloadError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result["status"] == "error":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Market structure source '{source_id}' was not found.")
    if result["status"] == "skipped":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(result["reason"]))
    return result
