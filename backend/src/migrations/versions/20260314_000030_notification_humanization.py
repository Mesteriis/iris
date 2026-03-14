"""notification humanization storage and control-plane seed

Revision ID: 20260314_000030
Revises: 20260312_000029
Create Date: 2026-03-14 12:40:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260314_000030"
down_revision = "20260312_000029"
branch_labels = None
depends_on = None


NOTIFICATION_CONSUMER = {
    "consumer_key": "notification_workers",
    "display_name": "Notification Workers",
    "domain": "notifications",
    "description": "Creates persisted humanized notifications from selected upstream events.",
    "implementation_key": "src.runtime.streams.workers._handle_notification_event",
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

    existing_consumer = bind.execute(
        sa.select(event_consumers.c.id).where(event_consumers.c.consumer_key == NOTIFICATION_CONSUMER["consumer_key"])
    ).first()
    if existing_consumer is None:
        bind.execute(event_consumers.insert(), [NOTIFICATION_CONSUMER])

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

    for route in NOTIFICATION_ROUTES:
        route_key = f'{route["event_type"]}:{NOTIFICATION_CONSUMER["consumer_key"]}:global:*:*'
        existing_route = bind.execute(
            sa.select(event_routes.c.id).where(event_routes.c.route_key == route_key)
        ).first()
        if existing_route is not None:
            continue
        bind.execute(
            event_routes.insert(),
            [
                {
                    "route_key": route_key,
                    "event_definition_id": event_id_by_type[str(route["event_type"])],
                    "consumer_id": consumer_id,
                    "status": "active",
                    "scope_type": "global",
                    "scope_value": None,
                    "environment": "*",
                    "filters_json": {},
                    "throttle_config_json": dict(route["throttle_config_json"]),
                    "shadow_config_json": {},
                    "notes": str(route["notes"]),
                    "priority": int(route["priority"]),
                    "system_managed": True,
                }
            ],
        )


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
