from src.apps.control_plane.contracts import AuditActor
from src.apps.control_plane.models import EventRoute, EventRouteAuditLog
from src.apps.control_plane.read_models import (
    EventRouteAuditLogReadModel,
    event_route_audit_log_read_model_from_orm,
)
from src.apps.control_plane.repositories import EventRouteAuditLogRepository


class AuditLogService:
    def __init__(self, repository: EventRouteAuditLogRepository) -> None:
        self._repository = repository

    async def log_route_change(
        self,
        *,
        route: EventRoute | None,
        route_key: str,
        action: str,
        actor: AuditActor,
        before: dict[str, object],
        after: dict[str, object],
        draft_id: int | None = None,
        topology_version_id: int | None = None,
    ) -> EventRouteAuditLogReadModel:
        row = await self._repository.add(
            EventRouteAuditLog(
                route_id=int(route.id) if route is not None else None,
                route_key_snapshot=route_key,
                draft_id=draft_id,
                topology_version_id=topology_version_id,
                action=action,
                actor=actor.actor,
                actor_mode=actor.actor_mode.value,
                reason=actor.reason,
                before_json=before,
                after_json=after,
                context_json=dict(actor.context),
            )
        )
        return event_route_audit_log_read_model_from_orm(row)

    async def list_recent(self, *, limit: int = 100) -> tuple[EventRouteAuditLogReadModel, ...]:
        return tuple(
            event_route_audit_log_read_model_from_orm(row) for row in await self._repository.list_recent(limit=limit)
        )


__all__ = ["AuditLogService"]
