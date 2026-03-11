"""Add pattern intelligence foundation.

Revision ID: 20260311_000010
Revises: 20260311_000009
Create Date: 2026-03-11 16:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000010"
down_revision: str | None = "20260311_000009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

PATTERN_FEATURES = (
    "pattern_detection",
    "pattern_clusters",
    "pattern_hierarchy",
    "market_regime_engine",
    "pattern_discovery_engine",
)

PATTERN_CATALOG = (
    ("head_shoulders", "structural", 4),
    ("inverse_head_shoulders", "structural", 4),
    ("double_top", "structural", 2),
    ("double_bottom", "structural", 2),
    ("triple_top", "structural", 3),
    ("triple_bottom", "structural", 3),
    ("ascending_triangle", "structural", 3),
    ("descending_triangle", "structural", 3),
    ("symmetrical_triangle", "structural", 3),
    ("rising_wedge", "structural", 3),
    ("falling_wedge", "structural", 3),
    ("bull_flag", "continuation", 2),
    ("bear_flag", "continuation", 2),
    ("pennant", "continuation", 2),
    ("cup_and_handle", "continuation", 4),
    ("breakout_retest", "continuation", 2),
    ("consolidation_breakout", "continuation", 2),
    ("rsi_divergence", "momentum", 2),
    ("macd_cross", "momentum", 1),
    ("macd_divergence", "momentum", 2),
    ("momentum_exhaustion", "momentum", 2),
    ("bollinger_squeeze", "volatility", 1),
    ("bollinger_expansion", "volatility", 1),
    ("atr_spike", "volatility", 1),
    ("volume_spike", "volume", 1),
    ("volume_climax", "volume", 2),
    ("volume_divergence", "volume", 2),
)


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_candles_coin_tf_ts_desc ON candles (coin_id, timeframe, timestamp DESC)")

    op.create_table(
        "pattern_features",
        sa.Column("feature_slug", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("feature_slug"),
    )
    op.bulk_insert(
        sa.table(
            "pattern_features",
            sa.column("feature_slug", sa.String()),
            sa.column("enabled", sa.Boolean()),
        ),
        [{"feature_slug": slug, "enabled": True} for slug in PATTERN_FEATURES],
    )

    op.create_table(
        "pattern_registry",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cpu_cost", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("slug"),
    )
    op.bulk_insert(
        sa.table(
            "pattern_registry",
            sa.column("slug", sa.String()),
            sa.column("category", sa.String()),
            sa.column("enabled", sa.Boolean()),
            sa.column("cpu_cost", sa.Integer()),
            sa.column("lifecycle_state", sa.String()),
        ),
        [
            {
                "slug": slug,
                "category": category,
                "enabled": True,
                "cpu_cost": cpu_cost,
                "lifecycle_state": "ACTIVE",
            }
            for slug, category, cpu_cost in PATTERN_CATALOG
        ],
    )

    op.create_table(
        "pattern_statistics",
        sa.Column("pattern_slug", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("success_rate", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_return", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_drawdown", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("temperature", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["pattern_slug"], ["pattern_registry.slug"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pattern_slug", "timeframe"),
    )
    op.create_index(
        "ix_pattern_statistics_temperature_desc",
        "pattern_statistics",
        ["timeframe", "temperature"],
        unique=False,
    )

    op.create_table(
        "discovered_patterns",
        sa.Column("structure_hash", sa.String(length=128), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_return", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_drawdown", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("confidence", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("structure_hash", "timeframe"),
    )

    op.create_table(
        "sectors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.execute(
        """
        INSERT INTO sectors (name, description)
        SELECT DISTINCT theme, initcap(replace(theme, '-', ' '))
        FROM coins
        WHERE theme IS NOT NULL AND btrim(theme) <> ''
        ON CONFLICT (name) DO NOTHING
        """
    )
    op.add_column("coins", sa.Column("sector_id", sa.Integer(), nullable=True))
    op.create_index("ix_coins_sector_id", "coins", ["sector_id"], unique=False)
    op.create_foreign_key("fk_coins_sector_id", "coins", "sectors", ["sector_id"], ["id"], ondelete="SET NULL")
    op.execute(
        """
        UPDATE coins
        SET sector_id = sectors.id
        FROM sectors
        WHERE coins.sector_id IS NULL
          AND coins.theme = sectors.name
        """
    )

    op.create_table(
        "sector_metrics",
        sa.Column("sector_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("sector_strength", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("relative_strength", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("capital_flow", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("volatility", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sector_id"], ["sectors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sector_id", "timeframe"),
    )

    op.create_table(
        "market_cycles",
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("cycle_phase", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("coin_id", "timeframe"),
    )

    op.add_column("signals", sa.Column("priority_score", sa.Float(53), nullable=False, server_default=sa.text("0")))
    op.add_column("signals", sa.Column("context_score", sa.Float(53), nullable=False, server_default=sa.text("1")))
    op.add_column("signals", sa.Column("regime_alignment", sa.Float(53), nullable=False, server_default=sa.text("1")))
    op.execute(
        """
        UPDATE signals
        SET priority_score = confidence,
            context_score = 1,
            regime_alignment = 1
        """
    )
    op.execute("CREATE INDEX ix_signals_priority_score_desc ON signals (priority_score DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_signals_priority_score_desc")
    op.drop_column("signals", "regime_alignment")
    op.drop_column("signals", "context_score")
    op.drop_column("signals", "priority_score")

    op.drop_table("market_cycles")
    op.drop_table("sector_metrics")
    op.drop_constraint("fk_coins_sector_id", "coins", type_="foreignkey")
    op.drop_index("ix_coins_sector_id", table_name="coins")
    op.drop_column("coins", "sector_id")
    op.drop_table("sectors")

    op.drop_table("discovered_patterns")
    op.drop_index("ix_pattern_statistics_temperature_desc", table_name="pattern_statistics")
    op.drop_table("pattern_statistics")
    op.drop_table("pattern_registry")
    op.drop_table("pattern_features")

    op.execute("DROP INDEX IF EXISTS ix_candles_coin_tf_ts_desc")
