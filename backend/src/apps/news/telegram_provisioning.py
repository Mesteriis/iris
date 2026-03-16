from typing import Any

from src.apps.news.contracts import (
    NewsSourceCreate,
    NewsSourceRead,
    TelegramBulkSubscribeRead,
    TelegramBulkSubscribeRequest,
    TelegramDialogSelection,
    TelegramDialogSubscribeResult,
    TelegramSourceFromDialogCreate,
)
from src.apps.news.exceptions import InvalidNewsSourceConfigurationError
from src.apps.news.polling import NewsService


class TelegramSourceProvisioningService:
    def __init__(self, uow) -> None:
        self._news = NewsService(uow)

    async def create_source_from_dialog(self, payload: TelegramSourceFromDialogCreate) -> NewsSourceRead:
        request = self._build_source_request(
            api_id=payload.api_id,
            api_hash=payload.api_hash,
            session_string=payload.session_string,
            dialog=payload.dialog,
        )
        return await self._news.create_source(request)

    async def bulk_subscribe(self, payload: TelegramBulkSubscribeRequest) -> TelegramBulkSubscribeRead:
        created: list[NewsSourceRead] = []
        results: list[TelegramDialogSubscribeResult] = []
        for dialog in payload.dialogs:
            try:
                source = await self.create_source_from_dialog(
                    TelegramSourceFromDialogCreate(
                        api_id=payload.api_id,
                        api_hash=payload.api_hash,
                        session_string=payload.session_string,
                        dialog=dialog,
                    )
                )
            except InvalidNewsSourceConfigurationError as exc:
                results.append(
                    TelegramDialogSubscribeResult(
                        title=dialog.title,
                        display_name=dialog.display_name or dialog.title,
                        status="skipped",
                        reason=str(exc),
                    )
                )
                continue
            created.append(source)
            results.append(
                TelegramDialogSubscribeResult(
                    title=dialog.title,
                    display_name=source.display_name,
                    status="created",
                    source_id=source.id,
                )
            )
        return TelegramBulkSubscribeRead(
            created_count=len(created),
            skipped_count=sum(1 for item in results if item.status != "created"),
            created=created,
            results=results,
        )

    @staticmethod
    def _build_source_request(
        *,
        api_id: int,
        api_hash: str,
        session_string: str,
        dialog: TelegramDialogSelection,
    ) -> NewsSourceCreate:
        entity_type = dialog.entity_type.strip().lower()
        if entity_type not in {"channel", "chat"}:
            raise InvalidNewsSourceConfigurationError(
                f"Telegram dialog '{dialog.title}' is not selectable for news polling."
            )
        display_name = (dialog.display_name or dialog.title).strip()
        settings: dict[str, Any] = {
            "entity_type": entity_type,
            "entity_id": int(dialog.entity_id),
        }
        if dialog.max_items_per_poll is not None:
            settings["max_results"] = int(dialog.max_items_per_poll)
        if dialog.username:
            settings["channel"] = f"@{dialog.username.lstrip('@')}"
        if entity_type == "channel":
            if dialog.access_hash in (None, ""):
                raise InvalidNewsSourceConfigurationError(
                    f"Telegram dialog '{dialog.title}' is missing access_hash for channel subscription."
                )
            settings["entity_access_hash"] = str(dialog.access_hash)
        return NewsSourceCreate(
            plugin_name="telegram_user",
            display_name=display_name,
            enabled=bool(dialog.enabled),
            credentials={
                "api_id": int(api_id),
                "api_hash": api_hash,
                "session_string": session_string,
            },
            settings=settings,
        )


__all__ = ["TelegramSourceProvisioningService"]
