"""Add analytics layer with TimescaleDB candle store and signals.

Revision ID: 20260311_000007
Revises: 20260311_000006
Create Date: 2026-03-11 02:05:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000007"
down_revision: str | None = "20260311_000006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    op.create_table(
        "candles",
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False, server_default=sa.text("15")),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(53), nullable=False),
        sa.Column("high", sa.Float(53), nullable=False),
        sa.Column("low", sa.Float(53), nullable=False),
        sa.Column("close", sa.Float(53), nullable=False),
        sa.Column("volume", sa.Float(53), nullable=True),
        sa.CheckConstraint("timeframe = 15", name="ck_candles_timeframe_15"),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("coin_id", "timeframe", "timestamp"),
    )
    op.create_index("ix_candles_coin_id_timestamp", "candles", ["coin_id", "timestamp"], unique=False)
    op.execute("SELECT create_hypertable('candles', by_range('timestamp'), if_not_exists => TRUE)")

    op.execute(
        """
        CREATE MATERIALIZED VIEW candles_1h
        WITH (timescaledb.continuous) AS
        SELECT
            coin_id,
            time_bucket(INTERVAL '1 hour', timestamp) AS bucket,
            first(open, timestamp) AS open,
            max(high) AS high,
            min(low) AS low,
            last(close, timestamp) AS close,
            sum(volume) AS volume
        FROM candles
        WHERE timeframe = 15
        GROUP BY coin_id, bucket
        WITH NO DATA
        """
    )
    op.execute(
        """
        CREATE MATERIALIZED VIEW candles_4h
        WITH (timescaledb.continuous) AS
        SELECT
            coin_id,
            time_bucket(INTERVAL '4 hours', timestamp) AS bucket,
            first(open, timestamp) AS open,
            max(high) AS high,
            min(low) AS low,
            last(close, timestamp) AS close,
            sum(volume) AS volume
        FROM candles
        WHERE timeframe = 15
        GROUP BY coin_id, bucket
        WITH NO DATA
        """
    )
    op.execute(
        """
        CREATE MATERIALIZED VIEW candles_1d
        WITH (timescaledb.continuous) AS
        SELECT
            coin_id,
            time_bucket(INTERVAL '1 day', timestamp) AS bucket,
            first(open, timestamp) AS open,
            max(high) AS high,
            min(low) AS low,
            last(close, timestamp) AS close,
            sum(volume) AS volume
        FROM candles
        WHERE timeframe = 15
        GROUP BY coin_id, bucket
        WITH NO DATA
        """
    )
    op.execute("CREATE INDEX ix_candles_1h_coin_id_bucket_desc ON candles_1h (coin_id, bucket DESC)")
    op.execute("CREATE INDEX ix_candles_4h_coin_id_bucket_desc ON candles_4h (coin_id, bucket DESC)")
    op.execute("CREATE INDEX ix_candles_1d_coin_id_bucket_desc ON candles_1d (coin_id, bucket DESC)")
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'candles_1h',
            start_offset => INTERVAL '3 hours',
            end_offset => INTERVAL '15 minutes',
            schedule_interval => INTERVAL '15 minutes',
            if_not_exists => TRUE
        )
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'candles_4h',
            start_offset => INTERVAL '12 hours',
            end_offset => INTERVAL '15 minutes',
            schedule_interval => INTERVAL '15 minutes',
            if_not_exists => TRUE
        )
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'candles_1d',
            start_offset => INTERVAL '3 days',
            end_offset => INTERVAL '15 minutes',
            schedule_interval => INTERVAL '15 minutes',
            if_not_exists => TRUE
        )
        """
    )

    op.alter_column(
        "coin_metrics",
        "price_current",
        type_=sa.Float(53),
        postgresql_using="price_current::double precision",
    )
    op.alter_column(
        "coin_metrics",
        "price_change_1h",
        type_=sa.Float(53),
        postgresql_using="price_change_1h::double precision",
    )
    op.alter_column(
        "coin_metrics",
        "price_change_24h",
        type_=sa.Float(53),
        postgresql_using="price_change_24h::double precision",
    )
    op.alter_column(
        "coin_metrics",
        "price_change_7d",
        type_=sa.Float(53),
        postgresql_using="price_change_7d::double precision",
    )
    op.alter_column(
        "coin_metrics",
        "volume_24h",
        type_=sa.Float(53),
        postgresql_using="volume_24h::double precision",
    )
    op.alter_column(
        "coin_metrics",
        "volatility",
        type_=sa.Float(53),
        postgresql_using="volatility::double precision",
    )
    op.alter_column(
        "coin_metrics",
        "market_cap",
        type_=sa.Float(53),
        postgresql_using="market_cap::double precision",
    )
    op.add_column("coin_metrics", sa.Column("ema_20", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("ema_50", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("sma_50", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("sma_200", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("rsi_14", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("macd", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("macd_signal", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("macd_histogram", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("atr_14", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("bb_upper", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("bb_middle", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("bb_lower", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("bb_width", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("adx_14", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("volume_change_24h", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("trend_score", sa.Integer(), nullable=True))
    op.add_column("coin_metrics", sa.Column("market_regime", sa.String(length=32), nullable=True))
    op.add_column(
        "coin_metrics",
        sa.Column("indicator_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.execute("CREATE INDEX ix_coin_metrics_trend_score_desc ON coin_metrics (trend_score DESC)")
    op.execute("CREATE INDEX ix_coin_metrics_volume_change_24h_desc ON coin_metrics (volume_change_24h DESC)")

    op.create_table(
        "indicator_cache",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("indicator", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(53), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indicator_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("feature_source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_indicator_cache_coin_id_timeframe_timestamp_desc",
        "indicator_cache",
        ["coin_id", "timeframe", "timestamp"],
        unique=False,
    )
    op.create_index(
        "ux_ind_cache_coin_tf_ind_ts_ver",
        "indicator_cache",
        ["coin_id", "timeframe", "indicator", "timestamp", "indicator_version"],
        unique=True,
    )

    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(53), nullable=False),
        sa.Column("candle_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ux_signals_coin_id_timeframe_candle_timestamp_signal_type",
        "signals",
        ["coin_id", "timeframe", "candle_timestamp", "signal_type"],
        unique=True,
    )
    op.create_index(
        "ix_signals_coin_id_timeframe_candle_timestamp",
        "signals",
        ["coin_id", "timeframe", "candle_timestamp"],
        unique=False,
    )

    op.execute(
        """
        UPDATE coins
        SET candles_config = (
            SELECT jsonb_agg(
                CASE
                    WHEN candle->>'interval' = '15m' AND (candle->>'retention_bars')::int < 20160 THEN
                        jsonb_set(candle, '{retention_bars}', to_jsonb(20160))
                    ELSE candle
                END
            )
            FROM jsonb_array_elements(coins.candles_config::jsonb) AS candle
        )
        WHERE EXISTS (
            SELECT 1
            FROM jsonb_array_elements(coins.candles_config::jsonb) AS candle
            WHERE candle->>'interval' = '15m'
              AND (candle->>'retention_bars')::int < 20160
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_coin_metrics_volume_change_24h_desc")
    op.execute("DROP INDEX IF EXISTS ix_coin_metrics_trend_score_desc")
    op.drop_column("coin_metrics", "indicator_version")
    op.drop_column("coin_metrics", "market_regime")
    op.drop_column("coin_metrics", "trend_score")
    op.drop_column("coin_metrics", "volume_change_24h")
    op.drop_column("coin_metrics", "adx_14")
    op.drop_column("coin_metrics", "bb_width")
    op.drop_column("coin_metrics", "bb_lower")
    op.drop_column("coin_metrics", "bb_middle")
    op.drop_column("coin_metrics", "bb_upper")
    op.drop_column("coin_metrics", "atr_14")
    op.drop_column("coin_metrics", "macd_histogram")
    op.drop_column("coin_metrics", "macd_signal")
    op.drop_column("coin_metrics", "macd")
    op.drop_column("coin_metrics", "rsi_14")
    op.drop_column("coin_metrics", "sma_200")
    op.drop_column("coin_metrics", "sma_50")
    op.drop_column("coin_metrics", "ema_50")
    op.drop_column("coin_metrics", "ema_20")
    op.alter_column(
        "coin_metrics",
        "market_cap",
        type_=sa.Numeric(30, 2),
        postgresql_using="market_cap::numeric",
    )
    op.alter_column(
        "coin_metrics",
        "volatility",
        type_=sa.Numeric(20, 8),
        postgresql_using="volatility::numeric",
    )
    op.alter_column(
        "coin_metrics",
        "volume_24h",
        type_=sa.Numeric(24, 8),
        postgresql_using="volume_24h::numeric",
    )
    op.alter_column(
        "coin_metrics",
        "price_change_7d",
        type_=sa.Numeric(20, 8),
        postgresql_using="price_change_7d::numeric",
    )
    op.alter_column(
        "coin_metrics",
        "price_change_24h",
        type_=sa.Numeric(20, 8),
        postgresql_using="price_change_24h::numeric",
    )
    op.alter_column(
        "coin_metrics",
        "price_change_1h",
        type_=sa.Numeric(20, 8),
        postgresql_using="price_change_1h::numeric",
    )
    op.alter_column(
        "coin_metrics",
        "price_current",
        type_=sa.Numeric(20, 8),
        postgresql_using="price_current::numeric",
    )

    op.drop_index("ix_signals_coin_id_timeframe_candle_timestamp", table_name="signals")
    op.drop_index("ux_signals_coin_id_timeframe_candle_timestamp_signal_type", table_name="signals")
    op.drop_table("signals")

    op.drop_index("ux_ind_cache_coin_tf_ind_ts_ver", table_name="indicator_cache")
    op.drop_index("ix_indicator_cache_coin_id_timeframe_timestamp_desc", table_name="indicator_cache")
    op.drop_table("indicator_cache")

    op.execute("SELECT remove_continuous_aggregate_policy('candles_1d', if_exists => TRUE)")
    op.execute("SELECT remove_continuous_aggregate_policy('candles_4h', if_exists => TRUE)")
    op.execute("SELECT remove_continuous_aggregate_policy('candles_1h', if_exists => TRUE)")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS candles_1d CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS candles_4h CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS candles_1h CASCADE")

    op.drop_index("ix_candles_coin_id_timestamp", table_name="candles")
    op.drop_table("candles")
