"""Add lazy investor decision engine storage.

Revision ID: 20260311_000012
Revises: 20260311_000011
Create Date: 2026-03-11 18:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000012"
down_revision: str | None = "20260311_000011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investment_decisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("score", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
    )
    op.execute(
        "CREATE INDEX ix_investment_decisions_coin_tf_created_desc "
        "ON investment_decisions (coin_id, timeframe, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_investment_decisions_score_desc "
        "ON investment_decisions (score DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_investment_decisions_score_desc")
    op.execute("DROP INDEX IF EXISTS ix_investment_decisions_coin_tf_created_desc")
    op.drop_table("investment_decisions")
