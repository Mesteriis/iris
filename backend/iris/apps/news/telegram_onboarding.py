from typing import Any

from iris.apps.news.contracts import (
    TelegramDialogRead,
    TelegramDialogsRequest,
    TelegramSessionCodeRequest,
    TelegramSessionCodeRequestRead,
    TelegramSessionConfirmRead,
    TelegramSessionConfirmRequest,
)
from iris.apps.news.exceptions import TelegramOnboardingError


class TelegramSessionOnboardingService:
    async def request_code(self, payload: TelegramSessionCodeRequest) -> TelegramSessionCodeRequestRead:
        TelegramClient, StringSession, _SessionPasswordNeededError, _tg_types = self._load_telethon()
        del _SessionPasswordNeededError
        del _tg_types
        try:
            async with TelegramClient(StringSession(), int(payload.api_id), payload.api_hash) as client:
                result = await client.send_code_request(payload.phone_number)
        except Exception as exc:  # pragma: no cover
            raise TelegramOnboardingError(str(exc)) from exc
        return TelegramSessionCodeRequestRead(
            status="code_sent",
            phone_number=payload.phone_number,
            phone_code_hash=str(result.phone_code_hash),
        )

    async def confirm_code(self, payload: TelegramSessionConfirmRequest) -> TelegramSessionConfirmRead:
        TelegramClient, StringSession, SessionPasswordNeededError, _tg_types = self._load_telethon()
        del _tg_types
        try:
            async with TelegramClient(StringSession(), int(payload.api_id), payload.api_hash) as client:
                try:
                    me = await client.sign_in(
                        phone=payload.phone_number,
                        code=payload.code,
                        phone_code_hash=payload.phone_code_hash,
                    )
                except SessionPasswordNeededError:
                    if not payload.password:
                        return TelegramSessionConfirmRead(status="password_required")
                    me = await client.sign_in(password=payload.password)
                me = me or await client.get_me()
                session_string = client.session.save()
        except Exception as exc:  # pragma: no cover
            raise TelegramOnboardingError(str(exc)) from exc

        display_name = " ".join(
            part for part in (getattr(me, "first_name", None), getattr(me, "last_name", None)) if part
        ).strip()
        return TelegramSessionConfirmRead(
            status="authorized",
            session_string=str(session_string),
            user_id=int(getattr(me, "id", 0)) if getattr(me, "id", None) is not None else None,
            username=str(getattr(me, "username", "")) or None,
            display_name=display_name or None,
        )

    async def list_dialogs(self, payload: TelegramDialogsRequest) -> list[TelegramDialogRead]:
        TelegramClient, StringSession, _SessionPasswordNeededError, tg_types = self._load_telethon()
        del _SessionPasswordNeededError
        try:
            async with TelegramClient(StringSession(payload.session_string), int(payload.api_id), payload.api_hash) as client:
                rows = [
                    self._serialize_dialog(dialog, tg_types)
                    async for dialog in client.iter_dialogs(limit=int(payload.limit))
                ]
        except Exception as exc:  # pragma: no cover
            raise TelegramOnboardingError(str(exc)) from exc
        return [row for row in rows if payload.include_users or row.entity_type != "user"]

    @staticmethod
    def _load_telethon() -> tuple[type[Any], type[Any], type[BaseException], Any]:
        try:
            from telethon import TelegramClient
            from telethon import types as tg_types
            from telethon.errors import SessionPasswordNeededError
            from telethon.sessions import StringSession
        except ImportError as exc:  # pragma: no cover
            raise TelegramOnboardingError(
                "telegram_user onboarding requires the optional 'telethon' dependency to be installed."
            ) from exc
        return TelegramClient, StringSession, SessionPasswordNeededError, tg_types

    @staticmethod
    def _serialize_dialog(dialog: Any, tg_types: Any) -> TelegramDialogRead:
        entity = dialog.entity
        username = str(getattr(entity, "username", "")) or None
        title = str(
            getattr(dialog, "title", "")
            or getattr(entity, "title", "")
            or username
            or getattr(entity, "first_name", "")
            or entity.id
        )
        if isinstance(entity, tg_types.Channel):
            entity_type = "channel"
            access_hash = str(getattr(entity, "access_hash", "")) or None
            settings_hint: dict[str, Any] = {
                "entity_type": "channel",
                "entity_id": int(entity.id),
            }
            if access_hash is not None:
                settings_hint["entity_access_hash"] = access_hash
            if username is not None:
                settings_hint["channel"] = f"@{username}"
        elif isinstance(entity, tg_types.Chat):
            entity_type = "chat"
            access_hash = None
            settings_hint = {
                "entity_type": "chat",
                "entity_id": int(entity.id),
                "channel": title,
            }
        else:
            entity_type = "user"
            access_hash = str(getattr(entity, "access_hash", "")) or None
            settings_hint = {
                "channel": f"@{username}" if username else title,
            }
        return TelegramDialogRead(
            entity_id=int(getattr(entity, "id", 0)),
            entity_type=entity_type,
            title=title,
            username=username,
            access_hash=access_hash,
            selectable=entity_type in {"channel", "chat"},
            settings_hint=settings_hint,
        )


__all__ = ["TelegramSessionOnboardingService"]
