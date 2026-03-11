"""Extend pattern success engine schema.

Revision ID: 20260311_000017
Revises: 20260311_000016
Create Date: 2026-03-11 22:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000017"
down_revision: str | None = "20260311_000016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("market_regime", sa.String(length=32), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_pattern_timestamp ON signals (signal_type, candle_timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_coin_timestamp ON signals (coin_id, candle_timestamp)")

    op.add_column("signal_history", sa.Column("market_regime", sa.String(length=32), nullable=True))
    op.add_column("signal_history", sa.Column("profit_after_24h", sa.Float(53), nullable=True))
    op.add_column("signal_history", sa.Column("profit_after_72h", sa.Float(53), nullable=True))
    op.add_column("signal_history", sa.Column("maximum_drawdown", sa.Float(53), nullable=True))

    op.add_column("pattern_statistics", sa.Column("market_regime", sa.String(length=32), nullable=True))
    op.add_column("pattern_statistics", sa.Column("total_signals", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("pattern_statistics", sa.Column("successful_signals", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("pattern_statistics", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("pattern_statistics", sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE pattern_statistics SET market_regime = 'all' WHERE market_regime IS NULL")
    op.execute("UPDATE pattern_statistics SET total_signals = sample_size")
    op.execute("UPDATE pattern_statistics SET successful_signals = ROUND(success_rate * sample_size)")
    op.execute("UPDATE pattern_statistics SET last_evaluated_at = updated_at")
    op.alter_column("pattern_statistics", "market_regime", nullable=False, server_default=sa.text("'all'"))

    op.drop_constraint("pattern_statistics_pkey", "pattern_statistics", type_="primary")
    op.create_primary_key(
        "pattern_statistics_pkey",
        "pattern_statistics",
        ["pattern_slug", "timeframe", "market_regime"],
    )
    op.drop_index("ix_pattern_statistics_temperature_desc", table_name="pattern_statistics")
    op.create_index(
        "ix_pattern_statistics_temperature_desc",
        "pattern_statistics",
        ["timeframe", "market_regime", "temperature"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pattern_statistics_temperature_desc", table_name="pattern_statistics")
    op.create_index(
        "ix_pattern_statistics_temperature_desc",
        "pattern_statistics",
        ["timeframe", "temperature"],
        unique=False,
    )
    op.drop_constraint("pattern_statistics_pkey", "pattern_statistics", type_="primary")
    op.create_primary_key("pattern_statistics_pkey", "pattern_statistics", ["pattern_slug", "timeframe"])
    op.drop_column("pattern_statistics", "last_evaluated_at")
    op.drop_column("pattern_statistics", "enabled")
    op.drop_column("pattern_statistics", "successful_signals")
    op.drop_column("pattern_statistics", "total_signals")
    op.drop_column("pattern_statistics", "market_regime")

    op.drop_column("signal_history", "maximum_drawdown")
    op.drop_column("signal_history", "profit_after_72h")
    op.drop_column("signal_history", "profit_after_24h")
    op.drop_column("signal_history", "market_regime")

    op.execute("DROP INDEX IF EXISTS ix_signals_coin_timestamp")
    op.execute("DROP INDEX IF EXISTS ix_signals_pattern_timestamp")
    op.drop_column("signals", "market_regime")
