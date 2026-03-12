from __future__ import annotations

from sqlalchemy import select

from src.apps.control_plane.enums import EventRouteScope, EventRouteStatus
from src.apps.control_plane.models import EventConsumer, EventDefinition, EventRoute, EventRouteAuditLog, TopologyConfigVersion
from src.runtime.streams.router import WORKER_EVENT_TYPES


def test_event_control_plane_seed_matches_legacy_worker_routes(db_session) -> None:
    expected_routes = {
        (event_type, consumer_key)
        for consumer_key, event_types in WORKER_EVENT_TYPES.items()
        for event_type in event_types
    }
    routes = db_session.scalars(select(EventRoute).order_by(EventRoute.id.asc())).all()

    actual_routes = {
        (str(route.event_definition.event_type), str(route.consumer.consumer_key))
        for route in routes
    }
    assert actual_routes == expected_routes
    assert {str(route.status) for route in routes} == {EventRouteStatus.ACTIVE.value}
    assert {str(route.scope_type) for route in routes} == {EventRouteScope.GLOBAL.value}
    assert {str(route.environment) for route in routes} == {"*"}


def test_event_control_plane_seed_creates_registry_version_and_audit_trail(db_session) -> None:
    control_event_types = db_session.scalars(
        select(EventDefinition.event_type)
        .where(EventDefinition.domain == "control_plane")
        .order_by(EventDefinition.event_type.asc())
    ).all()
    assert control_event_types == [
        "control.cache_invalidated",
        "control.route_created",
        "control.route_status_changed",
        "control.route_updated",
        "control.topology_published",
    ]

    published_version = db_session.scalar(
        select(TopologyConfigVersion).where(TopologyConfigVersion.version_number == 1).limit(1)
    )
    assert published_version is not None
    assert published_version.status == "published"
    assert published_version.snapshot_json["version_number"] == 1
    assert published_version.snapshot_json["routes"]

    audit_rows = db_session.scalars(select(EventRouteAuditLog)).all()
    assert len(audit_rows) == sum(len(event_types) for event_types in WORKER_EVENT_TYPES.values())
    assert {row.action for row in audit_rows} == {"bootstrapped"}


def test_event_control_plane_consumers_preserve_compatibility_contract(db_session) -> None:
    consumers = db_session.scalars(select(EventConsumer).order_by(EventConsumer.consumer_key.asc())).all()
    compatibility = {
        consumer.consumer_key: set(consumer.compatible_event_types_json)
        for consumer in consumers
    }
    assert compatibility == {consumer_key: set(event_types) for consumer_key, event_types in WORKER_EVENT_TYPES.items()}
