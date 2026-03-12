"""market structure source registry

Revision ID: 20260312_000025
Revises: 20260312_000024
Create Date: 2026-03-12 21:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_000025"
down_revision = "20260312_000024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_structure_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("plugin_name", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("auth_mode", sa.String(length=32), nullable=False),
        sa.Column("credentials_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("cursor_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_market_structure_sources_plugin_display_name "
        "ON market_structure_sources (plugin_name, display_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_structure_sources_enabled_updated_desc "
        "ON market_structure_sources (enabled, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_market_structure_sources_enabled_updated_desc")
    op.execute("DROP INDEX IF EXISTS ux_market_structure_sources_plugin_display_name")
    op.drop_table("market_structure_sources")
