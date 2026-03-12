"""Add signal history, feature snapshots and Timescale tuning.

Revision ID: 20260311_000015
Revises: 20260311_000014
Create Date: 2026-03-11 23:15:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000015"
down_revision: str | None = "20260311_000014"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                BEGIN
                    PERFORM set_chunk_time_interval('candles', INTERVAL '30 days');
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END;

                BEGIN
                    PERFORM add_dimension('candles', by_hash('coin_id', 8), if_not_exists => TRUE);
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END;

                BEGIN
                    EXECUTE
                        'ALTER TABLE candles SET ('
                        || 'timescaledb.compress, '
                        || 'timescaledb.compress_segmentby = ''coin_id,timeframe'', '
                        || 'timescaledb.compress_orderby = ''timestamp DESC'''
                        || ')';
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END;

                BEGIN
                    PERFORM add_compression_policy('candles', INTERVAL '90 days', if_not_exists => TRUE);
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END;
            END IF;
        END $$;
        """
    )

    op.create_table(
        "signal_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(53), nullable=False),
        sa.Column("candle_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_return", sa.Float(53), nullable=True),
        sa.Column("result_drawdown", sa.Float(53), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "coin_id",
            "timeframe",
            "signal_type",
            "candle_timestamp",
            name="ux_signal_history_coin_tf_type_ts",
        ),
    )
    op.execute(
        "CREATE INDEX ix_signal_history_coin_tf_ts_desc "
        "ON signal_history (coin_id, timeframe, candle_timestamp DESC)"
    )
    op.execute(
        "CREATE INDEX ix_signal_history_signal_type_coin_id "
        "ON signal_history (signal_type, coin_id)"
    )

    op.create_table(
        "feature_snapshots",
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_current", sa.Float(53), nullable=True),
        sa.Column("rsi_14", sa.Float(53), nullable=True),
        sa.Column("macd", sa.Float(53), nullable=True),
        sa.Column("trend_score", sa.Integer(), nullable=True),
        sa.Column("volatility", sa.Float(53), nullable=True),
        sa.Column("sector_strength", sa.Float(53), nullable=True),
        sa.Column("market_regime", sa.String(length=32), nullable=True),
        sa.Column("cycle_phase", sa.String(length=32), nullable=True),
        sa.Column("pattern_density", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cluster_score", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("coin_id", "timeframe", "timestamp"),
    )
    op.execute(
        "CREATE INDEX ix_feature_snapshots_coin_tf_ts_desc "
        "ON feature_snapshots (coin_id, timeframe, timestamp DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_feature_snapshots_coin_tf_ts_desc")
    op.drop_table("feature_snapshots")
    op.execute("DROP INDEX IF EXISTS ix_signal_history_signal_type_coin_id")
    op.execute("DROP INDEX IF EXISTS ix_signal_history_coin_tf_ts_desc")
    op.drop_table("signal_history")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                BEGIN
                    PERFORM remove_compression_policy('candles', if_exists => TRUE);
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END;
            END IF;
        END $$;
        """
    )
