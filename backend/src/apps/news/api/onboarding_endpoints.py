from __future__ import annotations

from fastapi import APIRouter, status

from src.apps.news.api.contracts import (
    NewsSourceRead,
    TelegramBulkSubscribeRead,
    TelegramBulkSubscribeRequest,
    TelegramDialogRead,
    TelegramDialogsRequest,
    TelegramSessionCodeRequest,
    TelegramSessionCodeRequestRead,
    TelegramSessionConfirmRead,
    TelegramSessionConfirmRequest,
    TelegramSourceFromDialogCreate,
    TelegramWizardRead,
)
from src.apps.news.api.deps import TelegramProvisioningDep, TelegramSessionOnboardingDep
from src.apps.news.api.errors import (
    news_error_responses,
    news_error_to_http,
    telegram_onboarding_error,
    telegram_request_code_error,
)
from src.apps.news.api.onboarding_wizard import telegram_wizard_spec
from src.apps.news.api.presenters import news_source_read, telegram_bulk_subscribe_read
from src.apps.news.exceptions import TelegramOnboardingError
from src.core.http.command_executor import execute_command
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["news:onboarding"])


@router.post(
    "/onboarding/telegram/session/request",
    response_model=TelegramSessionCodeRequestRead,
    status_code=status.HTTP_200_OK,
    summary="Request Telegram login code",
    responses=news_error_responses(503),
)
async def request_telegram_session_code(
    payload: TelegramSessionCodeRequest,
    service: TelegramSessionOnboardingDep,
    request_locale: RequestLocaleDep,
) -> TelegramSessionCodeRequestRead:
    try:
        return await service.request_code(payload)
    except TelegramOnboardingError as exc:
        raise telegram_request_code_error(exc, locale=request_locale) from exc


@router.post(
    "/onboarding/telegram/session/confirm",
    response_model=TelegramSessionConfirmRead,
    status_code=status.HTTP_200_OK,
    summary="Confirm Telegram login code",
    responses=news_error_responses(400),
)
async def confirm_telegram_session_code(
    payload: TelegramSessionConfirmRequest,
    service: TelegramSessionOnboardingDep,
    request_locale: RequestLocaleDep,
) -> TelegramSessionConfirmRead:
    try:
        return await service.confirm_code(payload)
    except TelegramOnboardingError as exc:
        raise telegram_onboarding_error(exc, locale=request_locale) from exc


@router.post(
    "/onboarding/telegram/dialogs",
    response_model=list[TelegramDialogRead],
    status_code=status.HTTP_200_OK,
    summary="List Telegram dialogs",
    responses=news_error_responses(400),
)
async def list_telegram_dialogs(
    payload: TelegramDialogsRequest,
    service: TelegramSessionOnboardingDep,
    request_locale: RequestLocaleDep,
) -> list[TelegramDialogRead]:
    try:
        return await service.list_dialogs(payload)
    except TelegramOnboardingError as exc:
        raise telegram_onboarding_error(exc, locale=request_locale) from exc


@router.get(
    "/onboarding/telegram/wizard",
    response_model=TelegramWizardRead,
    status_code=status.HTTP_200_OK,
    summary="Read Telegram onboarding wizard",
)
async def read_telegram_wizard(provisioning: TelegramProvisioningDep) -> TelegramWizardRead:
    del provisioning
    return telegram_wizard_spec()


@router.post(
    "/onboarding/telegram/sources",
    response_model=NewsSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Telegram news source from dialog",
    responses=news_error_responses(400),
)
async def create_telegram_source_from_dialog(
    payload: TelegramSourceFromDialogCreate,
    provisioning: TelegramProvisioningDep,
    request_locale: RequestLocaleDep,
) -> NewsSourceRead:
    return await execute_command(
        action=lambda: provisioning.service.create_source_from_dialog(payload),
        uow=provisioning.uow,
        presenter=news_source_read,
        translate_error=lambda exc: news_error_to_http(exc, locale=request_locale),
    )


@router.post(
    "/onboarding/telegram/sources/bulk",
    response_model=TelegramBulkSubscribeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk subscribe Telegram dialogs",
    responses=news_error_responses(400),
)
async def bulk_subscribe_telegram_sources(
    payload: TelegramBulkSubscribeRequest,
    provisioning: TelegramProvisioningDep,
    request_locale: RequestLocaleDep,
) -> TelegramBulkSubscribeRead:
    return await execute_command(
        action=lambda: provisioning.service.bulk_subscribe(payload),
        uow=provisioning.uow,
        presenter=telegram_bulk_subscribe_read,
        translate_error=lambda exc: news_error_to_http(exc, locale=request_locale),
    )
