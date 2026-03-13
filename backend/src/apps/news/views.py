from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.apps.news.exceptions import InvalidNewsSourceConfigurationError, TelegramOnboardingError, UnsupportedNewsPluginError
from src.apps.news.query_services import NewsQueryService
from src.apps.news.schemas import (
    NewsItemRead,
    NewsPluginRead,
    NewsSourceCreate,
    NewsSourceRead,
    NewsSourceUpdate,
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
from src.apps.news.services import NewsService, TelegramSessionOnboardingService, TelegramSourceProvisioningService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

router = APIRouter(tags=["news"])
DB_UOW = Depends(get_uow)


@router.get("/news/plugins", response_model=list[NewsPluginRead])
async def read_news_plugins(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[NewsPluginRead]:
    items = await NewsQueryService(uow.session).list_plugins()
    return [NewsPluginRead.model_validate(item) for item in items]


@router.get("/news/sources", response_model=list[NewsSourceRead])
async def read_news_sources(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[NewsSourceRead]:
    items = await NewsQueryService(uow.session).list_sources()
    return [NewsSourceRead.model_validate(item) for item in items]


@router.post("/news/sources", response_model=NewsSourceRead, status_code=status.HTTP_201_CREATED)
async def create_news_source(
    payload: NewsSourceCreate,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> NewsSourceRead:
    try:
        item = await NewsService(uow).create_source(payload)
        await uow.commit()
        return item
    except (InvalidNewsSourceConfigurationError, UnsupportedNewsPluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/news/sources/{source_id}", response_model=NewsSourceRead)
async def patch_news_source(
    source_id: int,
    payload: NewsSourceUpdate,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> NewsSourceRead:
    try:
        updated = await NewsService(uow).update_source(source_id, payload)
    except (InvalidNewsSourceConfigurationError, UnsupportedNewsPluginError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"News source '{source_id}' was not found.")
    await uow.commit()
    return updated


@router.delete("/news/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news_source(source_id: int, uow: BaseAsyncUnitOfWork = DB_UOW) -> None:
    deleted = await NewsService(uow).delete_source(source_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"News source '{source_id}' was not found.")
    await uow.commit()


@router.get("/news/items", response_model=list[NewsItemRead])
async def read_news_items(
    source_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[NewsItemRead]:
    items = await NewsQueryService(uow.session).list_items(source_id=source_id, limit=limit)
    return [NewsItemRead.model_validate(item) for item in items]


@router.post("/news/sources/{source_id}/jobs/run", status_code=status.HTTP_202_ACCEPTED)
async def run_news_source_job(
    source_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> dict[str, object]:
    from src.apps.news.tasks import poll_news_source_job

    source = await NewsQueryService(uow.session).get_source_read_by_id(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"News source '{source_id}' was not found.")

    await poll_news_source_job.kiq(source_id=int(source_id), limit=int(limit))
    return {
        "status": "queued",
        "source_id": int(source_id),
        "limit": int(limit),
    }


@router.post(
    "/news/onboarding/telegram/session/request",
    response_model=TelegramSessionCodeRequestRead,
    status_code=status.HTTP_200_OK,
)
async def request_telegram_session_code(payload: TelegramSessionCodeRequest) -> TelegramSessionCodeRequestRead:
    try:
        return await TelegramSessionOnboardingService().request_code(payload)
    except TelegramOnboardingError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post(
    "/news/onboarding/telegram/session/confirm",
    response_model=TelegramSessionConfirmRead,
    status_code=status.HTTP_200_OK,
)
async def confirm_telegram_session_code(payload: TelegramSessionConfirmRequest) -> TelegramSessionConfirmRead:
    try:
        return await TelegramSessionOnboardingService().confirm_code(payload)
    except TelegramOnboardingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/news/onboarding/telegram/dialogs",
    response_model=list[TelegramDialogRead],
    status_code=status.HTTP_200_OK,
)
async def list_telegram_dialogs(payload: TelegramDialogsRequest) -> list[TelegramDialogRead]:
    try:
        return await TelegramSessionOnboardingService().list_dialogs(payload)
    except TelegramOnboardingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/news/onboarding/telegram/wizard",
    response_model=TelegramWizardRead,
    status_code=status.HTTP_200_OK,
)
async def read_telegram_wizard() -> TelegramWizardRead:
    return TelegramSourceProvisioningService.wizard_spec()


@router.post(
    "/news/onboarding/telegram/sources",
    response_model=NewsSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_telegram_source_from_dialog(
    payload: TelegramSourceFromDialogCreate,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> NewsSourceRead:
    try:
        item = await TelegramSourceProvisioningService(uow).create_source_from_dialog(payload)
        await uow.commit()
        return item
    except InvalidNewsSourceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/news/onboarding/telegram/sources/bulk",
    response_model=TelegramBulkSubscribeRead,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_subscribe_telegram_sources(
    payload: TelegramBulkSubscribeRequest,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> TelegramBulkSubscribeRead:
    item = await TelegramSourceProvisioningService(uow).bulk_subscribe(payload)
    await uow.commit()
    return item
