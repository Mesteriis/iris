from collections.abc import Mapping

from src.apps.market_structure.constants import (
    MARKET_STRUCTURE_EVENT_SNAPSHOT_INGESTED,
    MARKET_STRUCTURE_EVENT_SOURCE_ALERTED,
    MARKET_STRUCTURE_EVENT_SOURCE_DELETED,
    MARKET_STRUCTURE_EVENT_SOURCE_HEALTH_UPDATED,
    MARKET_STRUCTURE_EVENT_SOURCE_QUARANTINED,
)
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.publisher import publish_event


class MarketStructureSideEffectDispatcher:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow

    def publish_source_deleted(self, *, payload: Mapping[str, object]) -> None:
        self._publish_after_commit(MARKET_STRUCTURE_EVENT_SOURCE_DELETED, payload)

    def publish_source_health_updated(self, *, payload: Mapping[str, object]) -> None:
        self._publish_after_commit(MARKET_STRUCTURE_EVENT_SOURCE_HEALTH_UPDATED, payload)

    def publish_source_alerted(self, *, payload: Mapping[str, object]) -> None:
        self._publish_after_commit(MARKET_STRUCTURE_EVENT_SOURCE_ALERTED, payload)

    def publish_source_quarantined(self, *, payload: Mapping[str, object]) -> None:
        self._publish_after_commit(MARKET_STRUCTURE_EVENT_SOURCE_QUARANTINED, payload)

    def publish_snapshot_ingested(self, *, payload: Mapping[str, object]) -> None:
        self._publish_after_commit(MARKET_STRUCTURE_EVENT_SNAPSHOT_INGESTED, payload)

    def _publish_after_commit(self, event_name: str, payload: Mapping[str, object]) -> None:
        self._uow.add_after_commit_action(
            lambda event_name=event_name, event_payload=dict(payload): publish_event(event_name, event_payload)
        )


__all__ = ["MarketStructureSideEffectDispatcher"]
