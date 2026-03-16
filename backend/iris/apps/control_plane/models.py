from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iris.core.db.session import Base


class EventDefinition(Base):
    __tablename__ = "event_definitions"
    __table_args__ = (
        Index("ux_event_definitions_event_type", "event_type", unique=True),
        Index("ix_event_definitions_domain_control", "domain", "is_control_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    is_control_event: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    payload_schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    routing_hints_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    routes: Mapped[list[EventRoute]] = relationship(
        "EventRoute",
        back_populates="event_definition",
        cascade="all, delete-orphan",
        order_by="EventRoute.id",
    )


class EventConsumer(Base):
    __tablename__ = "event_consumers"
    __table_args__ = (
        Index("ux_event_consumers_consumer_key", "consumer_key", unique=True),
        Index("ix_event_consumers_domain_mode", "domain", "delivery_mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    consumer_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    implementation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    delivery_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="worker", server_default="worker")
    delivery_stream: Mapped[str] = mapped_column(String(255), nullable=False)
    supports_shadow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    compatible_event_types_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    supported_filter_fields_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    supported_scopes_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    routes: Mapped[list[EventRoute]] = relationship(
        "EventRoute",
        back_populates="consumer",
        cascade="all, delete-orphan",
        order_by="EventRoute.id",
    )


class TopologyConfigVersion(Base):
    __tablename__ = "topology_config_versions"
    __table_args__ = (
        Index("ux_topology_config_versions_version_number", "version_number", unique=True),
        Index("ix_topology_config_versions_status_created_desc", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="published", server_default="published")
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    published_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system", server_default="system")
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    drafts: Mapped[list[TopologyDraft]] = relationship(
        "TopologyDraft",
        foreign_keys="TopologyDraft.base_version_id",
        back_populates="base_version",
    )


class TopologyDraft(Base):
    __tablename__ = "topology_drafts"
    __table_args__ = (
        Index("ix_topology_drafts_status_updated_desc", "status", "updated_at"),
        Index("ix_topology_drafts_base_version", "base_version_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default="draft")
    access_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="observe", server_default="observe")
    base_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("topology_config_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system", server_default="system")
    applied_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("topology_config_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    base_version: Mapped[TopologyConfigVersion | None] = relationship(
        "TopologyConfigVersion",
        foreign_keys=[base_version_id],
        back_populates="drafts",
    )
    applied_version: Mapped[TopologyConfigVersion | None] = relationship(
        "TopologyConfigVersion",
        foreign_keys=[applied_version_id],
    )
    changes: Mapped[list[TopologyDraftChange]] = relationship(
        "TopologyDraftChange",
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="TopologyDraftChange.id",
    )
    audit_logs: Mapped[list[EventRouteAuditLog]] = relationship(
        "EventRouteAuditLog",
        back_populates="draft",
        order_by="EventRouteAuditLog.created_at",
    )


class EventRoute(Base):
    __tablename__ = "event_routes"
    __table_args__ = (
        Index("ux_event_routes_route_key", "route_key", unique=True),
        Index("ix_event_routes_status_scope_env", "status", "scope_type", "environment"),
        Index("ix_event_routes_event_consumer", "event_definition_id", "consumer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_definition_id: Mapped[int] = mapped_column(
        ForeignKey("event_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    consumer_id: Mapped[int] = mapped_column(
        ForeignKey("event_consumers.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, default="global", server_default="global")
    scope_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="*", server_default="*")
    filters_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    throttle_config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    shadow_config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    system_managed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    event_definition: Mapped[EventDefinition] = relationship("EventDefinition", back_populates="routes")
    consumer: Mapped[EventConsumer] = relationship("EventConsumer", back_populates="routes")
    audit_logs: Mapped[list[EventRouteAuditLog]] = relationship(
        "EventRouteAuditLog",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="EventRouteAuditLog.created_at",
    )


class TopologyDraftChange(Base):
    __tablename__ = "topology_draft_changes"
    __table_args__ = (
        Index("ix_topology_draft_changes_draft_target", "draft_id", "target_route_key"),
        Index("ix_topology_draft_changes_type_created_desc", "change_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("topology_drafts.id", ondelete="CASCADE"), nullable=False)
    change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_route_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system", server_default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    draft: Mapped[TopologyDraft] = relationship("TopologyDraft", back_populates="changes")


class EventRouteAuditLog(Base):
    __tablename__ = "event_route_audit_logs"
    __table_args__ = (
        Index("ix_event_route_audit_logs_route_created_desc", "route_id", "created_at"),
        Index("ix_event_route_audit_logs_action_created_desc", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("event_routes.id", ondelete="SET NULL"), nullable=True)
    route_key_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("topology_drafts.id", ondelete="SET NULL"), nullable=True)
    topology_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("topology_config_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system", server_default="system")
    actor_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="control", server_default="control")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    before_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    after_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    route: Mapped[EventRoute | None] = relationship("EventRoute", back_populates="audit_logs")
    draft: Mapped[TopologyDraft | None] = relationship("TopologyDraft", back_populates="audit_logs")
    topology_version: Mapped[TopologyConfigVersion | None] = relationship("TopologyConfigVersion")


__all__ = [
    "EventConsumer",
    "EventDefinition",
    "EventRoute",
    "EventRouteAuditLog",
    "TopologyConfigVersion",
    "TopologyDraft",
    "TopologyDraftChange",
]
