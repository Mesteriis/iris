"""explanation surface

Revision ID: 20260314_000032
Revises: 20260314_000031
Create Date: 2026-03-14 00:32:00.000000
"""


import sqlalchemy as sa
from alembic import op

revision = "20260314_000032"
down_revision = "20260314_000031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_explanations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("explain_kind", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.BigInteger(), nullable=False),
        sa.Column("coin_id", sa.BigInteger(), sa.ForeignKey("coins.id", ondelete="SET NULL"), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("timeframe", sa.SmallInteger(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("bullets_json", sa.JSON(), nullable=False),
        sa.Column("refs_json", sa.JSON(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_name", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("subject_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_explanations_subject_lang "
        "ON ai_explanations (explain_kind, subject_id, language)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_explanations_kind_updated_desc "
        "ON ai_explanations (explain_kind, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_explanations_symbol_updated_desc "
        "ON ai_explanations (symbol, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_explanations_coin_updated_desc "
        "ON ai_explanations (coin_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ai_explanations_coin_updated_desc")
    op.execute("DROP INDEX IF EXISTS ix_ai_explanations_symbol_updated_desc")
    op.execute("DROP INDEX IF EXISTS ix_ai_explanations_kind_updated_desc")
    op.execute("DROP INDEX IF EXISTS ux_ai_explanations_subject_lang")
    op.drop_table("ai_explanations")
