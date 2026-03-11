"""Add liquidity and risk engine storage.

Revision ID: 20260311_000013
Revises: 20260311_000012
Create Date: 2026-03-11 21:15:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000013"
down_revision: str | None = "20260311_000012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_metrics",
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("liquidity_score", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("slippage_risk", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("volatility_risk", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("coin_id", "timeframe"),
    )
    op.execute(
        "CREATE INDEX ix_risk_metrics_liquidity_score_desc "
        "ON risk_metrics (liquidity_score DESC)"
    )

    op.create_table(
        "final_signals",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("risk_adjusted_score", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
    )
    op.execute(
        "CREATE INDEX ix_final_signals_coin_tf_created_desc "
        "ON final_signals (coin_id, timeframe, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_final_signals_risk_adjusted_score_desc "
        "ON final_signals (risk_adjusted_score DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_final_signals_risk_adjusted_score_desc")
    op.execute("DROP INDEX IF EXISTS ix_final_signals_coin_tf_created_desc")
    op.drop_table("final_signals")

    op.execute("DROP INDEX IF EXISTS ix_risk_metrics_liquidity_score_desc")
    op.drop_table("risk_metrics")
