"""notification humanization storage and control-plane seed

Revision ID: 20260314_000030
Revises: 20260312_000029
Create Date: 2026-03-14 12:40:00.000000
"""


import sqlalchemy as sa
from alembic import op

revision = "20260314_000030"
down_revision = "20260312_000029"
branch_labels = None
depends_on = None

DEFAULT_ENVIRONMENT = "*"
LEGACY_BOOTSTRAP_NOTES = "Bootstrapped from legacy runtime router"
LEGACY_BOOTSTRAP_REASON = "legacy_runtime_router_import"


NOTIFICATION_CONSUMER = {
    "consumer_key": "notification_workers",
    "display_name": "Notification Workers",
    "domain": "notifications",
    "description": "Creates persisted humanized notifications from selected upstream events.",
    "implementation_key": "iris.runtime.streams.workers._handle_notification_event",
    "delivery_mode": "worker",
    "delivery_stream": "iris:deliveries:notification_workers",
    "supports_shadow": False,
    "compatible_event_types_json": [
        "signal_created",
        "anomaly_detected",
        "decision_generated",
        "market_regime_changed",
        "portfolio_position_changed",
        "portfolio_balance_updated",
    ],
    "supported_filter_fields_json": ["symbol", "timeframe", "metadata"],
    "supported_scopes_json": ["global", "domain", "symbol", "timeframe", "environment"],
    "settings_json": {"capability": "notification_humanize"},
}

NOTIFICATION_ROUTES: list[dict[str, object]] = [
    {
        "event_type": "signal_created",
        "notes": "Humanize canonical signal events into persisted investor notifications.",
        "priority": 130,
        "throttle_config_json": {"limit": 60, "window_seconds": 60},
    },
    {
        "event_type": "anomaly_detected",
        "notes": "Humanize anomaly alerts into persisted investor notifications.",
        "priority": 120,
        "throttle_config_json": {"limit": 30, "window_seconds": 60},
    },
    {
        "event_type": "decision_generated",
        "notes": "Humanize generated investment decisions into persisted investor notifications.",
        "priority": 110,
        "throttle_config_json": {"limit": 60, "window_seconds": 60},
    },
    {
        "event_type": "market_regime_changed",
        "notes": "Humanize regime transitions into persisted investor notifications.",
        "priority": 120,
        "throttle_config_json": {"limit": 30, "window_seconds": 60},
    },
    {
        "event_type": "portfolio_position_changed",
        "notes": "Humanize portfolio position changes into persisted investor notifications.",
        "priority": 110,
        "throttle_config_json": {"limit": 60, "window_seconds": 60},
    },
    {
        "event_type": "portfolio_balance_updated",
        "notes": "Humanize balance sync updates into persisted investor notifications.",
        "priority": 140,
        "throttle_config_json": {"limit": 90, "window_seconds": 60},
    },
]

NOTIFICATION_CREATED_EVENT = {
    "event_type": "notification_created",
    "display_name": "Notification Created",
    "domain": "notifications",
    "description": "A persisted humanized notification artifact was created.",
    "is_control_event": False,
}


def _route_key(event_type: str) -> str:
    return f"{event_type}:{NOTIFICATION_CONSUMER['consumer_key']}:global:*:{DEFAULT_ENVIRONMENT}"


def _notification_consumer_snapshot() -> dict[str, object]:
    compatible_event_types = NOTIFICATION_CONSUMER["compatible_event_types_json"]
    return {
        "consumer_key": str(NOTIFICATION_CONSUMER["consumer_key"]),
        "display_name": str(NOTIFICATION_CONSUMER["display_name"]),
        "domain": str(NOTIFICATION_CONSUMER["domain"]),
        "delivery_stream": str(NOTIFICATION_CONSUMER["delivery_stream"]),
        "compatible_event_types": (
            [str(item) for item in compatible_event_types] if isinstance(compatible_event_types, list) else []
        ),
    }


def _notification_route_snapshot(route: dict[str, object]) -> dict[str, object]:
    return {
        "route_key": _route_key(str(route["event_type"])),
        "event_type": str(route["event_type"]),
        "consumer_key": str(NOTIFICATION_CONSUMER["consumer_key"]),
        "status": "active",
        "scope_type": "global",
        "environment": DEFAULT_ENVIRONMENT,
        "filters": {},
        "throttle": (
            dict(route["throttle_config_json"]) if isinstance(route["throttle_config_json"], dict) else {}
        ),
        "notes": str(route["notes"]),
        "priority": int(route["priority"]) if isinstance(route["priority"], int) else 0,
        "system_managed": True,
    }


def _merge_notification_snapshot(snapshot_json: object) -> dict[str, object]:
    snapshot = dict(snapshot_json) if isinstance(snapshot_json, dict) else {}

    consumer_rows = [
        dict(item) for item in snapshot.get("consumers", []) if isinstance(item, dict)
    ]
    route_rows = [
        dict(item) for item in snapshot.get("routes", []) if isinstance(item, dict)
    ]

    consumer_keys = {str(item.get("consumer_key", "")) for item in consumer_rows}
    if str(NOTIFICATION_CONSUMER["consumer_key"]) not in consumer_keys:
        consumer_rows.append(_notification_consumer_snapshot())

    route_keys = {str(item.get("route_key", "")) for item in route_rows}
    for route in NOTIFICATION_ROUTES:
        route_key = _route_key(str(route["event_type"]))
        if route_key not in route_keys:
            route_rows.append(_notification_route_snapshot(route))

    snapshot["consumers"] = consumer_rows
    snapshot["routes"] = route_rows
    return snapshot


def upgrade() -> None:
    op.create_table(
        "ai_notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("urgency", sa.String(length=16), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("refs_json", sa.JSON(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_name", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_event_type", sa.String(length=64), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=False),
        sa.Column("source_stream_id", sa.String(length=64), nullable=True),
        sa.Column("causation_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_notifications_source_event_lang "
        "ON ai_notifications (source_event_type, source_event_id, language)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_notifications_created_desc ON ai_notifications (created_at DESC)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_notifications_coin_created_desc "
        "ON ai_notifications (coin_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_notifications_event_created_desc "
        "ON ai_notifications (source_event_type, created_at DESC)"
    )

    bind = op.get_bind()
    event_definitions = sa.table(
        "event_definitions",
        sa.column("id", sa.Integer),
        sa.column("event_type", sa.String),
        sa.column("display_name", sa.String),
        sa.column("domain", sa.String),
        sa.column("description", sa.String),
        sa.column("is_control_event", sa.Boolean),
        sa.column("payload_schema_json", sa.JSON),
        sa.column("routing_hints_json", sa.JSON),
    )
    event_consumers = sa.table(
        "event_consumers",
        sa.column("id", sa.Integer),
        sa.column("consumer_key", sa.String),
        sa.column("display_name", sa.String),
        sa.column("domain", sa.String),
        sa.column("description", sa.String),
        sa.column("implementation_key", sa.String),
        sa.column("delivery_mode", sa.String),
        sa.column("delivery_stream", sa.String),
        sa.column("supports_shadow", sa.Boolean),
        sa.column("compatible_event_types_json", sa.JSON),
        sa.column("supported_filter_fields_json", sa.JSON),
        sa.column("supported_scopes_json", sa.JSON),
        sa.column("settings_json", sa.JSON),
    )
    event_routes = sa.table(
        "event_routes",
        sa.column("id", sa.Integer),
        sa.column("route_key", sa.String),
        sa.column("event_definition_id", sa.Integer),
        sa.column("consumer_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("scope_type", sa.String),
        sa.column("scope_value", sa.String),
        sa.column("environment", sa.String),
        sa.column("filters_json", sa.JSON),
        sa.column("throttle_config_json", sa.JSON),
        sa.column("shadow_config_json", sa.JSON),
        sa.column("notes", sa.String),
        sa.column("priority", sa.Integer),
        sa.column("system_managed", sa.Boolean),
    )
    topology_versions = sa.table(
        "topology_config_versions",
        sa.column("id", sa.Integer),
        sa.column("version_number", sa.Integer),
        sa.column("snapshot_json", sa.JSON),
    )
    audit_table = sa.table(
        "event_route_audit_logs",
        sa.column("route_id", sa.Integer),
        sa.column("route_key_snapshot", sa.String),
        sa.column("draft_id", sa.BigInteger),
        sa.column("topology_version_id", sa.Integer),
        sa.column("action", sa.String),
        sa.column("actor", sa.String),
        sa.column("actor_mode", sa.String),
        sa.column("reason", sa.String),
        sa.column("before_json", sa.JSON),
        sa.column("after_json", sa.JSON),
        sa.column("context_json", sa.JSON),
    )

    existing_notification_event = bind.execute(
        sa.select(event_definitions.c.id).where(event_definitions.c.event_type == NOTIFICATION_CREATED_EVENT["event_type"])
    ).first()
    if existing_notification_event is None:
        bind.execute(
            event_definitions.insert(),
            [
                {
                    **NOTIFICATION_CREATED_EVENT,
                    "payload_schema_json": {},
                    "routing_hints_json": {},
                }
            ],
        )
    else:
        bind.execute(
            event_definitions.update()
            .where(event_definitions.c.event_type == NOTIFICATION_CREATED_EVENT["event_type"])
            .values(
                display_name=NOTIFICATION_CREATED_EVENT["display_name"],
                domain=NOTIFICATION_CREATED_EVENT["domain"],
                description=NOTIFICATION_CREATED_EVENT["description"],
                is_control_event=NOTIFICATION_CREATED_EVENT["is_control_event"],
                payload_schema_json={},
                routing_hints_json={},
            )
        )

    existing_consumer = bind.execute(
        sa.select(event_consumers.c.id).where(event_consumers.c.consumer_key == NOTIFICATION_CONSUMER["consumer_key"])
    ).first()
    if existing_consumer is None:
        bind.execute(event_consumers.insert(), [NOTIFICATION_CONSUMER])
    else:
        bind.execute(
            event_consumers.update()
            .where(event_consumers.c.consumer_key == NOTIFICATION_CONSUMER["consumer_key"])
            .values(
                display_name=NOTIFICATION_CONSUMER["display_name"],
                domain=NOTIFICATION_CONSUMER["domain"],
                description=NOTIFICATION_CONSUMER["description"],
                implementation_key=NOTIFICATION_CONSUMER["implementation_key"],
                delivery_mode=NOTIFICATION_CONSUMER["delivery_mode"],
                delivery_stream=NOTIFICATION_CONSUMER["delivery_stream"],
                supports_shadow=NOTIFICATION_CONSUMER["supports_shadow"],
                compatible_event_types_json=NOTIFICATION_CONSUMER["compatible_event_types_json"],
                supported_filter_fields_json=NOTIFICATION_CONSUMER["supported_filter_fields_json"],
                supported_scopes_json=NOTIFICATION_CONSUMER["supported_scopes_json"],
                settings_json=NOTIFICATION_CONSUMER["settings_json"],
            )
        )

    consumer_id_row = bind.execute(
        sa.select(event_consumers.c.id).where(event_consumers.c.consumer_key == NOTIFICATION_CONSUMER["consumer_key"])
    ).first()
    if consumer_id_row is None:
        raise RuntimeError("notification worker consumer seed failed")
    consumer_id = int(consumer_id_row.id)

    event_id_by_type = {
        str(row.event_type): int(row.id)
        for row in bind.execute(
            sa.select(event_definitions.c.id, event_definitions.c.event_type).where(
                event_definitions.c.event_type.in_([route["event_type"] for route in NOTIFICATION_ROUTES])
            )
        )
    }
    if len(event_id_by_type) != len(NOTIFICATION_ROUTES):
        raise RuntimeError("notification worker routes require missing event definitions")

    for route in NOTIFICATION_ROUTES:
        route_key = _route_key(str(route["event_type"]))
        route_values = {
            "event_definition_id": event_id_by_type[str(route["event_type"])],
            "consumer_id": consumer_id,
            "status": "active",
            "scope_type": "global",
            "scope_value": None,
            "environment": DEFAULT_ENVIRONMENT,
            "filters_json": {},
            "throttle_config_json": (
                dict(route["throttle_config_json"])
                if isinstance(route["throttle_config_json"], dict)
                else {}
            ),
            "shadow_config_json": {},
            "notes": str(route["notes"]),
            "priority": int(route["priority"]) if isinstance(route["priority"], int) else 0,
            "system_managed": True,
        }
        existing_route = bind.execute(
            sa.select(event_routes.c.id).where(event_routes.c.route_key == route_key)
        ).first()
        if existing_route is not None:
            bind.execute(
                event_routes.update()
                .where(event_routes.c.route_key == route_key)
                .values(**route_values)
            )
            continue
        bind.execute(event_routes.insert(), [{"route_key": route_key, **route_values}])

    version_row = bind.execute(
        sa.select(topology_versions.c.id, topology_versions.c.snapshot_json)
        .where(topology_versions.c.version_number == 1)
        .limit(1)
    ).first()
    if version_row is not None:
        bind.execute(
            topology_versions.update()
            .where(topology_versions.c.id == int(version_row.id))
            .values(snapshot_json=_merge_notification_snapshot(version_row.snapshot_json))
        )

        route_key_to_id = {
            str(row.route_key): int(row.id)
            for row in bind.execute(
                sa.select(event_routes.c.id, event_routes.c.route_key).where(
                    event_routes.c.route_key.in_([_route_key(str(route["event_type"])) for route in NOTIFICATION_ROUTES])
                )
            )
        }
        existing_audit_route_keys = {
            str(row.route_key_snapshot)
            for row in bind.execute(
                sa.select(audit_table.c.route_key_snapshot).where(
                    audit_table.c.topology_version_id == int(version_row.id),
                    audit_table.c.action == "bootstrapped",
                    audit_table.c.route_key_snapshot.in_(list(route_key_to_id)),
                )
            )
        }

        missing_audit_rows = []
        for route in NOTIFICATION_ROUTES:
            route_key = _route_key(str(route["event_type"]))
            if route_key in existing_audit_route_keys:
                continue
            missing_audit_rows.append(
                {
                    "route_id": route_key_to_id[route_key],
                    "route_key_snapshot": route_key,
                    "draft_id": None,
                    "topology_version_id": int(version_row.id),
                    "action": "bootstrapped",
                    "actor": "system",
                    "actor_mode": "control",
                    "reason": LEGACY_BOOTSTRAP_REASON,
                    "before_json": {},
                    "after_json": {
                        "event_type": str(route["event_type"]),
                        "consumer_key": str(NOTIFICATION_CONSUMER["consumer_key"]),
                        "status": "active",
                        "scope_type": "global",
                        "environment": DEFAULT_ENVIRONMENT,
                    },
                    "context_json": {
                        "source": "legacy_runtime_router",
                        "migration_revision": revision,
                    },
                }
            )
        if missing_audit_rows:
            bind.execute(audit_table.insert(), missing_audit_rows)


def downgrade() -> None:
    op.execute(
        "DELETE FROM event_routes WHERE consumer_id IN "
        "(SELECT id FROM event_consumers WHERE consumer_key = 'notification_workers')"
    )
    op.execute("DELETE FROM event_consumers WHERE consumer_key = 'notification_workers'")
    op.execute("DELETE FROM event_definitions WHERE event_type = 'notification_created'")

    op.execute("DROP INDEX IF EXISTS ix_ai_notifications_event_created_desc")
    op.execute("DROP INDEX IF EXISTS ix_ai_notifications_coin_created_desc")
    op.execute("DROP INDEX IF EXISTS ix_ai_notifications_created_desc")
    op.execute("DROP INDEX IF EXISTS ux_ai_notifications_source_event_lang")
    op.drop_table("ai_notifications")
