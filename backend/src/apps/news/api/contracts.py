from __future__ import annotations

from typing import Literal

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
from src.core.http.contracts import HttpContract


class NewsSourceJobQueuedRead(HttpContract):
    status: Literal["queued"] = "queued"
    source_id: int
    limit: int


__all__ = [
    "NewsItemRead",
    "NewsPluginRead",
    "NewsSourceCreate",
    "NewsSourceJobQueuedRead",
    "NewsSourceRead",
    "NewsSourceUpdate",
    "TelegramBulkSubscribeRead",
    "TelegramBulkSubscribeRequest",
    "TelegramDialogRead",
    "TelegramDialogsRequest",
    "TelegramSessionCodeRequest",
    "TelegramSessionCodeRequestRead",
    "TelegramSessionConfirmRead",
    "TelegramSessionConfirmRequest",
    "TelegramSourceFromDialogCreate",
    "TelegramWizardRead",
]
