"""market structure snapshots for slow-path anomaly scans

Revision ID: 20260312_000024
Revises: 20260312_000023
Create Date: 2026-03-12 20:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_000024"
down_revision = "20260312_000023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_structure_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("venue", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_price", sa.Float(precision=53), nullable=True),
        sa.Column("mark_price", sa.Float(precision=53), nullable=True),
        sa.Column("index_price", sa.Float(precision=53), nullable=True),
        sa.Column("funding_rate", sa.Float(precision=53), nullable=True),
        sa.Column("open_interest", sa.Float(precision=53), nullable=True),
        sa.Column("basis", sa.Float(precision=53), nullable=True),
        sa.Column("liquidations_long", sa.Float(precision=53), nullable=True),
        sa.Column("liquidations_short", sa.Float(precision=53), nullable=True),
        sa.Column("volume", sa.Float(precision=53), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_market_structure_snapshots_coin_tf_venue_ts "
        "ON market_structure_snapshots (coin_id, timeframe, venue, timestamp)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_structure_snapshots_coin_tf_ts_desc "
        "ON market_structure_snapshots (coin_id, timeframe, timestamp DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_structure_snapshots_coin_venue_ts_desc "
        "ON market_structure_snapshots (coin_id, venue, timestamp DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_market_structure_snapshots_coin_venue_ts_desc")
    op.execute("DROP INDEX IF EXISTS ix_market_structure_snapshots_coin_tf_ts_desc")
    op.execute("DROP INDEX IF EXISTS ux_market_structure_snapshots_coin_tf_venue_ts")
    op.drop_table("market_structure_snapshots")
