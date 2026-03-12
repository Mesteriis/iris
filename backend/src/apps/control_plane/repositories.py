from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.apps.control_plane.models import (
    EventConsumer,
    EventDefinition,
    EventRoute,
    EventRouteAuditLog,
    TopologyConfigVersion,
    TopologyDraft,
    TopologyDraftChange,
)


class EventDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[EventDefinition]:
        return list(
            (
                await self._session.execute(
                    select(EventDefinition).order_by(EventDefinition.domain.asc(), EventDefinition.event_type.asc())
                )
            ).scalars().all()
        )

    async def get_by_event_type(self, event_type: str) -> EventDefinition | None:
        return (
            await self._session.execute(
                select(EventDefinition).where(EventDefinition.event_type == event_type).limit(1)
            )
        ).scalar_one_or_none()


class EventConsumerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[EventConsumer]:
        return list(
            (
                await self._session.execute(
                    select(EventConsumer).order_by(EventConsumer.domain.asc(), EventConsumer.consumer_key.asc())
                )
            ).scalars().all()
        )

    async def get_by_consumer_key(self, consumer_key: str) -> EventConsumer | None:
        return (
            await self._session.execute(
                select(EventConsumer).where(EventConsumer.consumer_key == consumer_key).limit(1)
            )
        ).scalar_one_or_none()


class EventRouteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[EventRoute]:
        return list(
            (
                await self._session.execute(
                    select(EventRoute)
                    .options(joinedload(EventRoute.event_definition), joinedload(EventRoute.consumer))
                    .order_by(EventRoute.id.asc())
                )
            ).scalars().unique().all()
        )

    async def get_by_route_key(self, route_key: str) -> EventRoute | None:
        return (
            await self._session.execute(
                select(EventRoute)
                .options(joinedload(EventRoute.event_definition), joinedload(EventRoute.consumer))
                .where(EventRoute.route_key == route_key)
                .limit(1)
            )
        ).scalar_one_or_none()

    async def add(self, route: EventRoute) -> EventRoute:
        self._session.add(route)
        await self._session.flush()
        await self._session.refresh(route)
        return route

    async def delete(self, route: EventRoute) -> None:
        await self._session.delete(route)
        await self._session.flush()


class EventRouteAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, audit_log: EventRouteAuditLog) -> EventRouteAuditLog:
        self._session.add(audit_log)
        await self._session.flush()
        return audit_log

    async def list_recent(self, *, limit: int = 100) -> list[EventRouteAuditLog]:
        return list(
            (
                await self._session.execute(
                    select(EventRouteAuditLog)
                    .options(joinedload(EventRouteAuditLog.route))
                    .order_by(EventRouteAuditLog.created_at.desc(), EventRouteAuditLog.id.desc())
                    .limit(max(limit, 1))
                )
            ).scalars().unique().all()
        )


class TopologyVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_published(self) -> TopologyConfigVersion | None:
        return (
            await self._session.execute(
                select(TopologyConfigVersion)
                .where(TopologyConfigVersion.status == "published")
                .order_by(TopologyConfigVersion.version_number.desc(), TopologyConfigVersion.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def add(self, version: TopologyConfigVersion) -> TopologyConfigVersion:
        self._session.add(version)
        await self._session.flush()
        await self._session.refresh(version)
        return version


class TopologyDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[TopologyDraft]:
        return list(
            (
                await self._session.execute(
                    select(TopologyDraft)
                    .options(joinedload(TopologyDraft.base_version), joinedload(TopologyDraft.applied_version))
                    .order_by(TopologyDraft.updated_at.desc(), TopologyDraft.id.desc())
                )
            ).scalars().unique().all()
        )

    async def get(self, draft_id: int) -> TopologyDraft | None:
        return (
            await self._session.execute(
                select(TopologyDraft)
                .options(joinedload(TopologyDraft.base_version), joinedload(TopologyDraft.applied_version))
                .where(TopologyDraft.id == draft_id)
                .limit(1)
            )
        ).scalar_one_or_none()

    async def add(self, draft: TopologyDraft) -> TopologyDraft:
        self._session.add(draft)
        await self._session.flush()
        await self._session.refresh(draft)
        return draft


class TopologyDraftChangeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_draft(self, draft_id: int) -> list[TopologyDraftChange]:
        return list(
            (
                await self._session.execute(
                    select(TopologyDraftChange)
                    .where(TopologyDraftChange.draft_id == draft_id)
                    .order_by(TopologyDraftChange.id.asc())
                )
            ).scalars().all()
        )

    async def add(self, change: TopologyDraftChange) -> TopologyDraftChange:
        self._session.add(change)
        await self._session.flush()
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
