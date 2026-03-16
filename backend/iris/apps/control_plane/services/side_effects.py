from collections.abc import Mapping

from iris.apps.control_plane.contracts import AuditActor
from iris.apps.control_plane.control_events import (
    CONTROL_CACHE_INVALIDATED,
    CONTROL_ROUTE_CREATED,
    CONTROL_ROUTE_STATUS_CHANGED,
    CONTROL_ROUTE_UPDATED,
    CONTROL_TOPOLOGY_PUBLISHED,
    publish_control_event,
)
from iris.apps.control_plane.read_models import EventRouteReadModel
from iris.core.db.uow import BaseAsyncUnitOfWork


class ControlPlaneSideEffectDispatcher:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow

    def publish_route_created(self, *, route: EventRouteReadModel, actor: AuditActor) -> None:
        self._publish_after_commit(
            CONTROL_ROUTE_CREATED,
            {
                "route_key": route.route_key,
                "event_type": route.event_type,
                "consumer_key": route.consumer_key,
                "status": route.status.value,
                "actor": actor.actor,
            },
        )

    def publish_route_updated(self, *, route: EventRouteReadModel, actor: AuditActor) -> None:
        self._publish_after_commit(
            CONTROL_ROUTE_UPDATED,
            {
                "route_key": route.route_key,
                "event_type": route.event_type,
                "consumer_key": route.consumer_key,
                "status": route.status.value,
                "actor": actor.actor,
            },
        )

    def publish_route_status_changed(self, *, route: EventRouteReadModel, actor: AuditActor) -> None:
        self._publish_after_commit(
            CONTROL_ROUTE_STATUS_CHANGED,
            {
                "route_key": route.route_key,
                "status": route.status.value,
                "actor": actor.actor,
            },
        )

    def publish_topology_published(self, *, draft_id: int, version_number: int, actor: AuditActor) -> None:
        self._publish_after_commit(
            CONTROL_TOPOLOGY_PUBLISHED,
            {
                "draft_id": int(draft_id),
                "version_number": int(version_number),
                "actor": actor.actor,
            },
        )

    def invalidate_cache(self, *, reason: str, actor: AuditActor, **payload: int | str) -> None:
        self._publish_after_commit(
            CONTROL_CACHE_INVALIDATED,
            {
                "reason": reason,
                "actor": actor.actor,
                **payload,
            },
        )

    def _publish_after_commit(self, event_type: str, payload: Mapping[str, object]) -> None:
        def _publish() -> None:
            publish_control_event(event_type, dict(payload))

        self._uow.add_after_commit_action(_publish)


__all__ = ["ControlPlaneSideEffectDispatcher"]
