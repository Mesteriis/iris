from __future__ import annotations

from fastapi import APIRouter, status

from src.apps.market_structure.api.contracts import (
    BinanceMarketStructureSourceCreateRequest,
    BybitMarketStructureSourceCreateRequest,
    ManualPushMarketStructureSourceCreateRequest,
    ManualWebhookMarketStructureSourceCreateRequest,
    MarketStructureOnboardingRead,
    MarketStructureSourceRead,
    MarketStructureWebhookRegistrationRead,
)
from src.apps.market_structure.api.deps import MarketStructureProvisioningDep
from src.apps.market_structure.api.errors import market_structure_error_responses, market_structure_error_to_http
from src.apps.market_structure.api.presenters import (
    market_structure_source_read,
    market_structure_webhook_registration_read,
)
from src.core.http.command_executor import execute_command

router = APIRouter(tags=["market-structure:onboarding"])


@router.get(
    "/onboarding/wizard",
    response_model=MarketStructureOnboardingRead,
    summary="Read market structure onboarding wizard",
)
async def read_market_structure_onboarding_wizard(
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureOnboardingRead:
    return provisioning.service.wizard_spec()


@router.post(
    "/onboarding/sources/binance-usdm",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Binance USD-M market structure source",
    responses=market_structure_error_responses(400),
)
async def create_binance_market_structure_source(
    payload: BinanceMarketStructureSourceCreateRequest,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureSourceRead:
    return await execute_command(
        action=lambda: provisioning.service.create_binance_source(payload),
        uow=provisioning.uow,
        presenter=market_structure_source_read,
        translate_error=market_structure_error_to_http,
    )


@router.post(
    "/onboarding/sources/bybit-derivatives",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Bybit derivatives market structure source",
    responses=market_structure_error_responses(400),
)
async def create_bybit_market_structure_source(
    payload: BybitMarketStructureSourceCreateRequest,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureSourceRead:
    return await execute_command(
        action=lambda: provisioning.service.create_bybit_source(payload),
        uow=provisioning.uow,
        presenter=market_structure_source_read,
        translate_error=market_structure_error_to_http,
    )


@router.post(
    "/onboarding/sources/manual-push",
    response_model=MarketStructureSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual push market structure source",
    responses=market_structure_error_responses(400),
)
async def create_manual_market_structure_source(
    payload: ManualPushMarketStructureSourceCreateRequest,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureSourceRead:
    return await execute_command(
        action=lambda: provisioning.service.create_manual_source(payload),
        uow=provisioning.uow,
        presenter=market_structure_source_read,
        translate_error=market_structure_error_to_http,
    )


@router.post(
    "/onboarding/sources/liqscope-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Liqscope webhook source",
    responses=market_structure_error_responses(400),
)
async def create_liqscope_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureWebhookRegistrationRead:
    return await execute_command(
        action=lambda: provisioning.service.create_liqscope_webhook_source(payload),
        uow=provisioning.uow,
        presenter=market_structure_webhook_registration_read,
        translate_error=market_structure_error_to_http,
    )


@router.post(
    "/onboarding/sources/liquidation-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create liquidation webhook source",
    responses=market_structure_error_responses(400),
)
async def create_liquidation_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureWebhookRegistrationRead:
    return await execute_command(
        action=lambda: provisioning.service.create_liquidation_webhook_source(payload),
        uow=provisioning.uow,
        presenter=market_structure_webhook_registration_read,
        translate_error=market_structure_error_to_http,
    )


@router.post(
    "/onboarding/sources/derivatives-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create derivatives webhook source",
    responses=market_structure_error_responses(400),
)
async def create_derivatives_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureWebhookRegistrationRead:
    return await execute_command(
        action=lambda: provisioning.service.create_derivatives_webhook_source(payload),
        uow=provisioning.uow,
        presenter=market_structure_webhook_registration_read,
        translate_error=market_structure_error_to_http,
    )


@router.post(
    "/onboarding/sources/coinglass-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Coinglass webhook source",
    responses=market_structure_error_responses(400),
)
async def create_coinglass_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureWebhookRegistrationRead:
    return await execute_command(
        action=lambda: provisioning.service.create_coinglass_webhook_source(payload),
        uow=provisioning.uow,
        presenter=market_structure_webhook_registration_read,
        translate_error=market_structure_error_to_http,
    )


@router.post(
    "/onboarding/sources/hyblock-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Hyblock webhook source",
    responses=market_structure_error_responses(400),
)
async def create_hyblock_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureWebhookRegistrationRead:
    return await execute_command(
        action=lambda: provisioning.service.create_hyblock_webhook_source(payload),
        uow=provisioning.uow,
        presenter=market_structure_webhook_registration_read,
        translate_error=market_structure_error_to_http,
    )


@router.post(
    "/onboarding/sources/coinalyze-webhook",
    response_model=MarketStructureWebhookRegistrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Coinalyze webhook source",
    responses=market_structure_error_responses(400),
)
async def create_coinalyze_market_structure_webhook_source(
    payload: ManualWebhookMarketStructureSourceCreateRequest,
    provisioning: MarketStructureProvisioningDep,
) -> MarketStructureWebhookRegistrationRead:
    return await execute_command(
        action=lambda: provisioning.service.create_coinalyze_webhook_source(payload),
        uow=provisioning.uow,
        presenter=market_structure_webhook_registration_read,
        translate_error=market_structure_error_to_http,
    )
