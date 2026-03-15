from __future__ import annotations

from typing import Any

from src.apps.hypothesis_engine.prompts import PromptLoader
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.market_data.domain import ensure_utc
from src.apps.notifications.constants import (
    AI_EVENT_NOTIFICATION_CREATED,
    CANONICAL_REF_FIELDS,
    DEFAULT_NOTIFICATION_PROMPT_NAME,
    DEFAULT_NOTIFICATION_TIMEFRAME,
    EVENT_PROMPT_NAMES,
    SUPPORTED_NOTIFICATION_SOURCE_EVENTS,
)
from src.apps.notifications.contracts import (
    NotificationCreationResult,
    NotificationCreationStatus,
    NotificationPendingEvent,
)
from src.apps.notifications.models import AINotification
from src.apps.notifications.query_services import NotificationQueryService
from src.apps.notifications.repositories import NotificationRepository
from src.apps.notifications.services.humanization_service import (
    NotificationHumanizationService,
    resolve_effective_language,
)
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.types import IrisEvent


class NotificationService(PersistenceComponent):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="notifications",
            component_name="NotificationService",
        )
        self._uow = uow
        self._repo = NotificationRepository(uow.session)
        self._queries = NotificationQueryService(uow.session)
        self._prompt_loader = PromptLoader(HypothesisQueryService(uow.session))
        self._humanizer = NotificationHumanizationService()

    async def create_from_event(self, event: IrisEvent) -> NotificationCreationResult:
        if event.event_type not in SUPPORTED_NOTIFICATION_SOURCE_EVENTS or event.coin_id <= 0:
            return NotificationCreationResult(status=NotificationCreationStatus.SKIPPED, reason="event_not_supported")
        coin = await self._queries.get_coin_context(int(event.coin_id))
        if coin is None:
            return NotificationCreationResult(status=NotificationCreationStatus.SKIPPED, reason="coin_not_found")
        effective_timeframe = int(event.timeframe) if int(event.timeframe) > 0 else DEFAULT_NOTIFICATION_TIMEFRAME
        context: dict[str, Any] = {
            "event_type": event.event_type,
            "coin_id": int(event.coin_id),
            "timeframe": effective_timeframe,
            "timestamp": ensure_utc(event.timestamp).isoformat(),
            "stream_id": event.stream_id,
            "event_id": event.event_id,
            "causation_id": event.causation_id,
            "correlation_id": event.correlation_id,
            "payload": dict(event.payload),
            "symbol": coin.symbol,
            "sector": coin.sector_code,
        }
        for key in ("language", "locale", "requested_provider"):
            value = event.payload.get(key)
            if value is not None and str(value).strip():
                context[key] = str(value).strip()
        effective_language = resolve_effective_language(context)
        existing = await self._repo.get_by_source_event(
            source_event_type=event.event_type,
            source_event_id=event.event_id,
            language=effective_language,
        )
        if existing is not None:
            self._log_debug(
                "service.create_notification_from_event.duplicate",
                mode="write",
                source_event_type=event.event_type,
                source_event_id=event.event_id,
                language=effective_language,
            )
            return NotificationCreationResult(
                status=NotificationCreationStatus.SKIPPED,
                notification_id=int(existing.id),
                reason="notification_already_exists",
            )

        prompt_name = EVENT_PROMPT_NAMES.get(event.event_type, DEFAULT_NOTIFICATION_PROMPT_NAME)
        prompt = await self._prompt_loader.load(prompt_name)
        humanized = await self._humanizer.generate(context, prompt=prompt)
        metadata = humanized.metadata
        notification = await self._repo.add_notification(
            AINotification(
                coin_id=int(event.coin_id),
                symbol=str(coin.symbol),
                sector=str(coin.sector_code) if coin.sector_code is not None else None,
                timeframe=effective_timeframe,
                title=humanized.title,
                message=humanized.message,
                severity=humanized.severity,
                urgency=humanized.urgency,
                language=metadata.effective_language,
                refs_json=self._build_refs(event=event, symbol=coin.symbol, sector=coin.sector_code),
                context_json={
                    "symbol": coin.symbol,
                    "sector": coin.sector_code,
                    "trigger_timestamp": ensure_utc(event.timestamp).isoformat(),
                    "source_payload": dict(event.payload),
                    "ai_execution": metadata.as_dict(),
                },
                provider=str(metadata.actual_provider or ""),
                model=metadata.model,
                prompt_name=metadata.prompt_name,
                prompt_version=int(metadata.prompt_version),
                source_event_type=event.event_type,
                source_event_id=event.event_id,
                source_stream_id=event.stream_id,
                causation_id=event.causation_id,
                correlation_id=event.correlation_id,
            )
        )
        return NotificationCreationResult(
            status=NotificationCreationStatus.CREATED,
            notification_id=int(notification.id),
            pending_events=(
                NotificationPendingEvent(
                    event_type=AI_EVENT_NOTIFICATION_CREATED,
                    payload={
                        "coin_id": int(notification.coin_id),
                        "timeframe": int(notification.timeframe),
                        "timestamp": ensure_utc(event.timestamp),
                        "notification_id": int(notification.id),
                        "severity": notification.severity,
                        "urgency": notification.urgency,
                        "language": notification.language,
                        "source_event_type": notification.source_event_type,
                    },
                ),
            ),
        )

    def _build_refs(
        self,
        *,
        event: IrisEvent,
        symbol: str,
        sector: str | None,
    ) -> dict[str, Any]:
        canonical_fields = {
            key: event.payload[key]
            for key in CANONICAL_REF_FIELDS.get(event.event_type, ())
            if key in event.payload and event.payload[key] is not None
        }
        return {
            "coin_id": int(event.coin_id),
            "symbol": symbol,
            "sector": sector,
            "timeframe": int(event.timeframe),
            "source_event_type": event.event_type,
            "source_event_id": event.event_id,
            "source_stream_id": event.stream_id,
            "canonical_fields": canonical_fields,
        }


__all__ = ["NotificationService"]
