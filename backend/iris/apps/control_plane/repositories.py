from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from iris.apps.control_plane.models import (
    EventConsumer,
    EventDefinition,
    EventRoute,
    EventRouteAuditLog,
    TopologyConfigVersion,
    TopologyDraft,
    TopologyDraftChange,
)
from iris.core.db.persistence import AsyncRepository


class EventDefinitionRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", repository_name="EventDefinitionRepository")

    async def list_all(self) -> list[EventDefinition]:
        self._log_debug("repo.list_event_definitions", mode="read")
        rows = list(
            (
                await self.session.execute(
                    select(EventDefinition).order_by(EventDefinition.domain.asc(), EventDefinition.event_type.asc())
                )
            )
            .scalars()
            .all()
        )
        self._log_debug("repo.list_event_definitions.result", mode="read", count=len(rows))
        return rows

    async def get_by_event_type(self, event_type: str) -> EventDefinition | None:
        self._log_debug("repo.get_event_definition", mode="read", event_type=event_type)
        row = (
            await self.session.execute(select(EventDefinition).where(EventDefinition.event_type == event_type).limit(1))
        ).scalar_one_or_none()
        self._log_debug("repo.get_event_definition.result", mode="read", found=row is not None)
        return row


class EventConsumerRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", repository_name="EventConsumerRepository")

    async def list_all(self) -> list[EventConsumer]:
        self._log_debug("repo.list_event_consumers", mode="read")
        rows = list(
            (
                await self.session.execute(
                    select(EventConsumer).order_by(EventConsumer.domain.asc(), EventConsumer.consumer_key.asc())
                )
            )
            .scalars()
            .all()
        )
        self._log_debug("repo.list_event_consumers.result", mode="read", count=len(rows))
        return rows

    async def get_by_consumer_key(self, consumer_key: str) -> EventConsumer | None:
        self._log_debug("repo.get_event_consumer", mode="read", consumer_key=consumer_key)
        row = (
            await self.session.execute(select(EventConsumer).where(EventConsumer.consumer_key == consumer_key).limit(1))
        ).scalar_one_or_none()
        self._log_debug("repo.get_event_consumer.result", mode="read", found=row is not None)
        return row


class EventRouteRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", repository_name="EventRouteRepository")

    async def list_all(self) -> list[EventRoute]:
        self._log_debug("repo.list_routes", mode="read", loading_profile="with_relations")
        rows = list(
            (
                await self.session.execute(
                    select(EventRoute)
                    .options(joinedload(EventRoute.event_definition), joinedload(EventRoute.consumer))
                    .order_by(EventRoute.id.asc())
                )
            )
            .scalars()
            .unique()
            .all()
        )
        self._log_debug("repo.list_routes.result", mode="read", count=len(rows))
        return rows

    async def get_by_route_key(self, route_key: str) -> EventRoute | None:
        self._log_debug("repo.get_route", mode="read", route_key=route_key, loading_profile="with_relations")
        row = (
            await self.session.execute(
                select(EventRoute)
                .options(joinedload(EventRoute.event_definition), joinedload(EventRoute.consumer))
                .where(EventRoute.route_key == route_key)
                .limit(1)
            )
        ).scalar_one_or_none()
        self._log_debug("repo.get_route.result", mode="read", found=row is not None)
        return row

    async def add(self, route: EventRoute) -> EventRoute:
        self._log_info("repo.add_route", mode="write", route_key=route.route_key)
        self.session.add(route)
        await self.session.flush()
        await self.session.refresh(route)
        return route

    async def delete(self, route: EventRoute) -> None:
        self._log_info("repo.delete_route", mode="write", route_key=route.route_key)
        await self.session.delete(route)
        await self.session.flush()


class EventRouteAuditLogRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", repository_name="EventRouteAuditLogRepository")

    async def add(self, audit_log: EventRouteAuditLog) -> EventRouteAuditLog:
        self._log_info(
            "repo.add_route_audit_log", mode="write", route_key=audit_log.route_key_snapshot, action=audit_log.action
        )
        self.session.add(audit_log)
        await self.session.flush()
        return audit_log

    async def list_recent(self, *, limit: int = 100) -> list[EventRouteAuditLog]:
        self._log_debug("repo.list_recent_route_audit_logs", mode="read", limit=limit)
        rows = list(
            (
                await self.session.execute(
                    select(EventRouteAuditLog)
                    .options(joinedload(EventRouteAuditLog.route))
                    .order_by(EventRouteAuditLog.created_at.desc(), EventRouteAuditLog.id.desc())
                    .limit(max(limit, 1))
                )
            )
            .scalars()
            .unique()
            .all()
        )
        self._log_debug("repo.list_recent_route_audit_logs.result", mode="read", count=len(rows))
        return rows


class TopologyVersionRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", repository_name="TopologyVersionRepository")

    async def get_latest_published(self) -> TopologyConfigVersion | None:
        self._log_debug("repo.get_latest_published_topology_version", mode="read")
        row = (
            await self.session.execute(
                select(TopologyConfigVersion)
                .where(TopologyConfigVersion.status == "published")
                .order_by(TopologyConfigVersion.version_number.desc(), TopologyConfigVersion.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        self._log_debug("repo.get_latest_published_topology_version.result", mode="read", found=row is not None)
        return row

    async def add(self, version: TopologyConfigVersion) -> TopologyConfigVersion:
        self._log_info("repo.add_topology_version", mode="write", version_number=int(version.version_number))
        self.session.add(version)
        await self.session.flush()
        await self.session.refresh(version)
        return version


class TopologyDraftRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", repository_name="TopologyDraftRepository")

    async def list_all(self) -> list[TopologyDraft]:
        self._log_debug("repo.list_topology_drafts", mode="read", loading_profile="with_relations")
        rows = list(
            (
                await self.session.execute(
                    select(TopologyDraft)
                    .options(joinedload(TopologyDraft.base_version), joinedload(TopologyDraft.applied_version))
                    .order_by(TopologyDraft.updated_at.desc(), TopologyDraft.id.desc())
                )
            )
            .scalars()
            .unique()
            .all()
        )
        self._log_debug("repo.list_topology_drafts.result", mode="read", count=len(rows))
        return rows

    async def get(self, draft_id: int) -> TopologyDraft | None:
        self._log_debug("repo.get_topology_draft", mode="read", draft_id=draft_id, loading_profile="with_relations")
        row = (
            await self.session.execute(
                select(TopologyDraft)
                .options(joinedload(TopologyDraft.base_version), joinedload(TopologyDraft.applied_version))
                .where(TopologyDraft.id == draft_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        self._log_debug("repo.get_topology_draft.result", mode="read", found=row is not None)
        return row

    async def add(self, draft: TopologyDraft) -> TopologyDraft:
        self._log_info("repo.add_topology_draft", mode="write", name=draft.name)
        self.session.add(draft)
        await self.session.flush()
        await self.session.refresh(draft)
        return draft


class TopologyDraftChangeRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", repository_name="TopologyDraftChangeRepository")

    async def list_by_draft(self, draft_id: int) -> list[TopologyDraftChange]:
        self._log_debug("repo.list_topology_draft_changes", mode="read", draft_id=draft_id)
        rows = list(
            (
                await self.session.execute(
                    select(TopologyDraftChange)
                    .where(TopologyDraftChange.draft_id == draft_id)
                    .order_by(TopologyDraftChange.id.asc())
                )
            )
            .scalars()
            .all()
        )
        self._log_debug("repo.list_topology_draft_changes.result", mode="read", count=len(rows))
        return rows

    async def add(self, change: TopologyDraftChange) -> TopologyDraftChange:
        self._log_info(
            "repo.add_topology_draft_change",
            mode="write",
            draft_id=int(change.draft_id),
            change_type=change.change_type,
        )
        self.session.add(change)
        await self.session.flush()
        return change


__all__ = [
    "EventConsumerRepository",
    "EventDefinitionRepository",
    "EventRouteAuditLogRepository",
    "EventRouteRepository",
    "TopologyDraftChangeRepository",
    "TopologyDraftRepository",
    "TopologyVersionRepository",
]
