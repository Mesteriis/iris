from typing import Literal

from iris.apps.news.schemas import (
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
from iris.core.http.contracts import AcceptedResponse


class NewsSourceJobAcceptedRead(AcceptedResponse):
    operation_type: Literal["news.source.poll"] = "news.source.poll"
    source_id: int
    limit: int


__all__ = [
    "NewsItemRead",
    "NewsPluginRead",
    "NewsSourceCreate",
    "NewsSourceJobAcceptedRead",
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
