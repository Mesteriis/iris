"""news source plugins

Revision ID: 20260312_000022
Revises: 20260312_000021
Create Date: 2026-03-12 14:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_000022"
down_revision = "20260312_000021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_sources",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("plugin_name", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_news_sources_plugin_display_name "
        "ON news_sources (plugin_name, display_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_news_sources_enabled_updated_desc "
        "ON news_sources (enabled, updated_at DESC)"
    )

    op.create_table(
        "news_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("news_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plugin_name", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("author_handle", sa.String(length=120), nullable=True),
        sa.Column("channel_name", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("symbol_hints", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_news_items_source_external "
        "ON news_items (source_id, external_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_news_items_published_desc "
        "ON news_items (published_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_news_items_plugin_published_desc "
        "ON news_items (plugin_name, published_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_news_items_plugin_published_desc")
    op.execute("DROP INDEX IF EXISTS ix_news_items_published_desc")
    op.execute("DROP INDEX IF EXISTS ux_news_items_source_external")
    op.drop_table("news_items")
    op.execute("DROP INDEX IF EXISTS ix_news_sources_enabled_updated_desc")
    op.execute("DROP INDEX IF EXISTS ux_news_sources_plugin_display_name")
    op.drop_table("news_sources")
