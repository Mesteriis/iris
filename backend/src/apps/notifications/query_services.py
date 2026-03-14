from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.market_data.models import Coin
from src.apps.notifications.models import AINotification
from src.apps.notifications.read_models import (
    NotificationCoinContextReadModel,
    NotificationReadModel,
    notification_read_model_from_orm,
)
from src.core.db.persistence import AsyncQueryService


class NotificationQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="notifications", service_name="NotificationQueryService")

    async def list_notifications(
        self,
        *,
        limit: int,
        coin_id: int | None = None,
        source_event_type: str | None = None,
        language: str | None = None,
    ) -> tuple[NotificationReadModel, ...]:
        self._log_debug(
            "query.list_notifications",
            mode="read",
            limit=limit,
            coin_id=coin_id,
            source_event_type=source_event_type,
            language=language,
        )
        stmt = select(AINotification).order_by(AINotification.created_at.desc()).limit(limit)
        if coin_id is not None:
            stmt = stmt.where(AINotification.coin_id == coin_id)
        if source_event_type is not None:
            stmt = stmt.where(AINotification.source_event_type == source_event_type)
        if language is not None:
            stmt = stmt.where(AINotification.language == language)
        rows = (await self.session.execute(stmt)).scalars().all()
        items = tuple(notification_read_model_from_orm(item) for item in rows)
        self._log_debug("query.list_notifications.result", mode="read", count=len(items))
        return items

    async def get_notification_read_by_id(self, notification_id: int) -> NotificationReadModel | None:
        self._log_debug("query.get_notification_read_by_id", mode="read", notification_id=notification_id)
        notification = await self.session.get(AINotification, notification_id)
        if notification is None:
            self._log_debug("query.get_notification_read_by_id.result", mode="read", found=False)
            return None
        item = notification_read_model_from_orm(notification)
        self._log_debug("query.get_notification_read_by_id.result", mode="read", found=True)
        return item

    async def get_coin_context(self, coin_id: int) -> NotificationCoinContextReadModel | None:
        self._log_debug("query.get_notification_coin_context", mode="read", coin_id=coin_id)
        row = await self.session.execute(
            select(Coin.id, Coin.symbol, Coin.sector_code).where(Coin.id == coin_id).limit(1)
        )
        result = row.first()
        if result is None:
            self._log_debug("query.get_notification_coin_context.result", mode="read", found=False)
            return None
        item = NotificationCoinContextReadModel(
            coin_id=int(result.id),
            symbol=str(result.symbol),
            sector_code=str(result.sector_code) if result.sector_code is not None else None,
        )
        self._log_debug("query.get_notification_coin_context.result", mode="read", found=True)
        return item


__all__ = ["NotificationQueryService"]
