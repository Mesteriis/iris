from collections.abc import Mapping

from iris.apps.market_structure.constants import (
    MARKET_STRUCTURE_EVENT_SNAPSHOT_INGESTED,
    MARKET_STRUCTURE_EVENT_SOURCE_ALERTED,
    MARKET_STRUCTURE_EVENT_SOURCE_DELETED,
    MARKET_STRUCTURE_EVENT_SOURCE_HEALTH_UPDATED,
    MARKET_STRUCTURE_EVENT_SOURCE_QUARANTINED,
)
from iris.core.db.uow import BaseAsyncUnitOfWork
from iris.runtime.streams.publisher import publish_event


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
        def _publish() -> None:
            publish_event(event_name, dict(payload))

        self._uow.add_after_commit_action(_publish)


__all__ = ["MarketStructureSideEffectDispatcher"]
