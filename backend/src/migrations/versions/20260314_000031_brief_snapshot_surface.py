"""brief snapshot surface

Revision ID: 20260314_000031
Revises: 20260314_000030
Create Date: 2026-03-14 00:31:00.000000
"""


import sqlalchemy as sa
from alembic import op

revision = "20260314_000031"
down_revision = "20260314_000030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_briefs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("brief_kind", sa.String(length=32), nullable=False),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("coin_id", sa.BigInteger(), sa.ForeignKey("coins.id", ondelete="SET NULL"), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("bullets_json", sa.JSON(), nullable=False),
        sa.Column("refs_json", sa.JSON(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_name", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_briefs_scope_lang "
        "ON ai_briefs (brief_kind, scope_key, language)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_briefs_kind_updated_desc "
        "ON ai_briefs (brief_kind, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_briefs_symbol_updated_desc "
        "ON ai_briefs (symbol, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_briefs_coin_updated_desc "
        "ON ai_briefs (coin_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ai_briefs_coin_updated_desc")
    op.execute("DROP INDEX IF EXISTS ix_ai_briefs_symbol_updated_desc")
    op.execute("DROP INDEX IF EXISTS ix_ai_briefs_kind_updated_desc")
    op.execute("DROP INDEX IF EXISTS ux_ai_briefs_scope_lang")
    op.drop_table("ai_briefs")
