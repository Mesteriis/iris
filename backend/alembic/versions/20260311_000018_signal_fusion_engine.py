"""signal fusion engine

Revision ID: 20260311_000018
Revises: 20260311_000017
Create Date: 2026-03-11 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_000018"
down_revision = "20260311_000017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_decisions_coin_tf_created_desc "
        "ON market_decisions (coin_id, timeframe, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_decisions_confidence_desc "
        "ON market_decisions (confidence DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_signals_coin_tf_ts "
        "ON signals (coin_id, timeframe, candle_timestamp DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_signals_coin_tf_ts")
    op.execute("DROP INDEX IF EXISTS ix_market_decisions_confidence_desc")
    op.execute("DROP INDEX IF EXISTS ix_market_decisions_coin_tf_created_desc")
    op.drop_table("market_decisions")
