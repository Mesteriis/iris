from typing import Any

from src.apps.control_plane.contracts import (
    AuditActor,
    DraftChangeCommand,
    DraftCreateCommand,
    RouteMutationCommand,
    TopologyDiffItem,
)
from src.apps.control_plane.engines.route_engine import command_from_payload, merge_route_command, route_to_snapshot
from src.apps.control_plane.enums import (
    EventAuditAction,
    TopologyDraftChangeType,
    TopologyDraftStatus,
    TopologyVersionStatus,
)
from src.apps.control_plane.exceptions import (
    TopologyDraftConcurrencyConflict,
    TopologyDraftNotFound,
    TopologyDraftStateError,
)
from src.apps.control_plane.models import EventRoute, TopologyConfigVersion, TopologyDraft, TopologyDraftChange
from src.apps.control_plane.query_services import (
    TopologyDraftQueryService,
    TopologyQueryService,
    topology_snapshot_payload,
)
from src.apps.control_plane.read_models import (
    EventRouteReadModel,
    TopologyDraftChangeReadModel,
    TopologyDraftReadModel,
    route_read_model_from_orm,
    topology_draft_change_read_model_from_orm,
    topology_draft_read_model_from_orm,
)
from src.apps.control_plane.repositories import (
    EventConsumerRepository,
    EventDefinitionRepository,
    EventRouteAuditLogRepository,
    EventRouteRepository,
    TopologyDraftChangeRepository,
    TopologyDraftRepository,
    TopologyVersionRepository,
)
from src.apps.market_data.domain import utc_now
from src.core.db.persistence import thaw_json_value
from src.core.db.uow import BaseAsyncUnitOfWork

from .audit_service import AuditLogService
from .draft_route_mutation_flow import DraftRouteMutationFlow
from .results import TopologyDraftLifecycleResult
from .route_mutation_writer import RouteMutationWriter
from .side_effects import ControlPlaneSideEffectDispatcher


class TopologyDraftService:
    def __init__(
        self,
        uow: BaseAsyncUnitOfWork,
        *,
        dispatcher: ControlPlaneSideEffectDispatcher | None = None,
        audit_service: AuditLogService | None = None,
    ) -> None:
        self._uow = uow
        self._session = uow.session
        self._drafts = TopologyDraftRepository(self._session)
        self._changes = TopologyDraftChangeRepository(self._session)
        self._routes = EventRouteRepository(self._session)
        self._events = EventDefinitionRepository(self._session)
        self._consumers = EventConsumerRepository(self._session)
        self._versions = TopologyVersionRepository(self._session)
        self._dispatcher = dispatcher or ControlPlaneSideEffectDispatcher(uow)
        self._audit = audit_service or AuditLogService(EventRouteAuditLogRepository(self._session))
        self._writer = RouteMutationWriter(
            uow=uow,
            events=self._events,
            consumers=self._consumers,
            routes=self._routes,
        )
        self._mutation_flow = DraftRouteMutationFlow(writer=self._writer, audit_service=self._audit)

    async def create_draft(self, command: DraftCreateCommand) -> TopologyDraftReadModel:
        latest_version = await self._versions.get_latest_published()
        draft = TopologyDraft(
            name=command.name,
            description=command.description,
            status=TopologyDraftStatus.DRAFT.value,
            access_mode=command.access_mode.value,
            base_version_id=int(latest_version.id) if latest_version is not None else None,
            created_by=command.created_by,
        )
        draft = await self._drafts.add(draft)
        return topology_draft_read_model_from_orm(draft)

    async def list_drafts(self) -> tuple[TopologyDraftReadModel, ...]:
        return tuple(topology_draft_read_model_from_orm(row) for row in await self._drafts.list_all())

    async def add_change(self, draft_id: int, command: DraftChangeCommand) -> TopologyDraftChangeReadModel:
        draft = await self._require_draft(draft_id)
        if draft.status != TopologyDraftStatus.DRAFT.value:
            raise TopologyDraftStateError(f"Draft '{draft_id}' is not editable.")
        change = TopologyDraftChange(
            draft_id=int(draft.id),
            change_type=command.change_type.value,
            target_route_key=command.target_route_key,
            payload_json=dict(command.payload),
            created_by=command.created_by,
        )
        change = await self._changes.add(change)
        draft.updated_at = utc_now()
        await self._uow.flush()
        return topology_draft_change_read_model_from_orm(change)

    async def preview_diff(self, draft_id: int) -> tuple[TopologyDiffItem, ...]:
        return await TopologyDraftQueryService(self._session).preview_diff(draft_id)

    async def apply_draft(self, draft_id: int, *, actor: AuditActor) -> TopologyDraftLifecycleResult:
        draft = await self._require_draft(draft_id)
        if draft.status != TopologyDraftStatus.DRAFT.value:
            raise TopologyDraftStateError(f"Draft '{draft_id}' is not editable.")

        latest_version = await self._versions.get_latest_published()
        latest_version_id = int(latest_version.id) if latest_version is not None else None
        if draft.base_version_id != latest_version_id:
            raise TopologyDraftConcurrencyConflict(
                draft_id,
                expected_version=int(draft.base_version.version_number) if draft.base_version is not None else None,
                current_version=int(latest_version.version_number) if latest_version is not None else None,
            )

        changes = await self._changes.list_by_draft(int(draft.id))
        if not changes:
            raise TopologyDraftStateError(f"Draft '{draft_id}' has no changes to apply.")

        next_version_number = (int(latest_version.version_number) if latest_version is not None else 0) + 1
        version = await self._versions.add(
            TopologyConfigVersion(
                version_number=next_version_number,
                status=TopologyVersionStatus.PUBLISHED.value,
                summary=f"Applied draft '{draft.name}'",
                published_by=actor.actor,
                snapshot_json={},
            )
        )
        for change in changes:
            await self._apply_change(
                change,
                draft_id=int(draft.id),
                topology_version_id=int(version.id),
                actor=actor,
            )
        version.snapshot_json = await self._build_published_snapshot(version=version)
        draft.status = TopologyDraftStatus.APPLIED.value
        draft.applied_version_id = int(version.id)
        draft.applied_at = utc_now()
        draft.updated_at = draft.applied_at
        await self._uow.flush()
        self._dispatcher.publish_topology_published(
            draft_id=int(draft.id),
            version_number=int(version.version_number),
            actor=actor,
        )
        self._dispatcher.invalidate_cache(
            reason="topology_published",
            draft_id=int(draft.id),
            version_number=int(version.version_number),
            actor=actor,
        )
        return TopologyDraftLifecycleResult(
            draft=topology_draft_read_model_from_orm(draft),
            published_version_number=int(version.version_number),
        )

    async def discard_draft(self, draft_id: int, *, actor: AuditActor) -> TopologyDraftReadModel:
        draft = await self._require_draft(draft_id)
        if draft.status != TopologyDraftStatus.DRAFT.value:
            raise TopologyDraftStateError(f"Draft '{draft_id}' cannot be discarded from status '{draft.status}'.")

        for item in await self.preview_diff(draft_id):
            await self._audit.log_route_change(
                route=None,
                route_key=item.route_key,
                action=EventAuditAction.DRAFT_DISCARDED.value,
                actor=actor,
                before=thaw_json_value(item.before),
                after=thaw_json_value(item.after),
                draft_id=int(draft.id),
            )
        draft.status = TopologyDraftStatus.DISCARDED.value
        draft.discarded_at = utc_now()
        draft.updated_at = draft.discarded_at
        await self._uow.flush()
        return topology_draft_read_model_from_orm(draft)

    async def _apply_change(
        self,
        change: TopologyDraftChange,
        *,
        draft_id: int,
        topology_version_id: int,
        actor: AuditActor,
    ) -> None:
        change_type = TopologyDraftChangeType(change.change_type)
        payload = dict(change.payload_json or {})
        if change_type == TopologyDraftChangeType.ROUTE_CREATED:
            await self._mutation_flow.create(
                command_from_payload(payload),
                actor=actor,
                draft_id=draft_id,
                topology_version_id=topology_version_id,
            )
            return

        if change.target_route_key is None:
            raise TopologyDraftStateError(f"Draft change '{change.id}' is missing a target route key.")

        route = await self._writer.require_route(change.target_route_key)
        before = route_to_snapshot(route_read_model_from_orm(route))
        if change_type == TopologyDraftChangeType.ROUTE_STATUS_CHANGED:
            result = await self._writer.change_status(
                route,
                status=str(payload["status"]),
                notes=str(payload["notes"]) if payload.get("notes") is not None else None,
            )
            await self._audit.log_route_change(
                route=route,
                route_key=route.route_key,
                action=EventAuditAction.STATUS_CHANGED.value,
                actor=actor,
                before=before,
                after=route_to_snapshot(result),
                draft_id=draft_id,
                topology_version_id=topology_version_id,
            )
            return

        if change_type == TopologyDraftChangeType.ROUTE_UPDATED:
            await self._mutation_flow.update(
                route,
                command=merge_route_command(before, payload),
                actor=actor,
                draft_id=draft_id,
                topology_version_id=topology_version_id,
                before=before,
            )
            return

        if change_type == TopologyDraftChangeType.ROUTE_DELETED:
            await self._routes.delete(route)
            await self._audit.log_route_change(
                route=None,
                route_key=str(before["route_key"]),
                action=EventAuditAction.DELETED.value,
                actor=actor,
                before=before,
                after={},
                draft_id=draft_id,
                topology_version_id=topology_version_id,
            )
            return

        raise TopologyDraftStateError(f"Unsupported draft change type '{change.change_type}'.")

    async def _require_draft(self, draft_id: int) -> TopologyDraft:
        draft = await self._drafts.get(draft_id)
        if draft is None:
            raise TopologyDraftNotFound(f"Draft '{draft_id}' does not exist.")
        return draft

    async def _build_published_snapshot(self, *, version: TopologyConfigVersion) -> dict[str, Any]:
        snapshot = topology_snapshot_payload(await TopologyQueryService(self._session).build_snapshot())
        snapshot["version_number"] = int(version.version_number)
        snapshot["created_at"] = version.created_at.isoformat() if version.created_at is not None else None
        return snapshot


__all__ = ["TopologyDraftService"]
