"""cross market intelligence and prediction memory

Revision ID: 20260311_000020
Revises: 20260311_000019
Create Date: 2026-03-11 19:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_000020"
down_revision = "20260311_000019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coins", sa.Column("sector", sa.String(length=32), nullable=True))
    op.execute("UPDATE coins SET sector = COALESCE(NULLIF(theme, ''), 'infrastructure') WHERE sector IS NULL")
    op.alter_column("coins", "sector", existing_type=sa.String(length=32), nullable=False, server_default="infrastructure")

    op.add_column("sector_metrics", sa.Column("avg_price_change_24h", sa.Float(precision=53), nullable=False, server_default="0"))
    op.add_column("sector_metrics", sa.Column("avg_volume_change_24h", sa.Float(precision=53), nullable=False, server_default="0"))
    op.add_column("sector_metrics", sa.Column("trend", sa.String(length=16), nullable=True))

    op.create_table(
        "coin_relations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("leader_coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("follower_coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("correlation", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("lag_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ux_coin_relations_leader_follower",
        "coin_relations",
        ["leader_coin_id", "follower_coin_id"],
        unique=True,
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_coin_relations_follower_confidence_desc "
        "ON coin_relations (follower_coin_id, confidence DESC)"
    )

    op.create_table(
        "market_predictions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("prediction_type", sa.String(length=64), nullable=False),
        sa.Column("leader_coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prediction_event", sa.String(length=64), nullable=False),
        sa.Column("expected_move", sa.String(length=16), nullable=False),
        sa.Column("lag_hours", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
    )
    op.create_index(
        "ix_market_predictions_status_evaluation_time",
        "market_predictions",
        ["status", "evaluation_time"],
        unique=False,
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_predictions_leader_target_created_desc "
        "ON market_predictions (leader_coin_id, target_coin_id, created_at DESC)"
    )

    op.create_table(
        "prediction_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("market_predictions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actual_move", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("profit", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_prediction_results_prediction_id", "prediction_results", ["prediction_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_prediction_results_prediction_id", table_name="prediction_results")
    op.drop_table("prediction_results")
    op.execute("DROP INDEX IF EXISTS ix_market_predictions_leader_target_created_desc")
    op.drop_index("ix_market_predictions_status_evaluation_time", table_name="market_predictions")
    op.drop_table("market_predictions")
    op.execute("DROP INDEX IF EXISTS ix_coin_relations_follower_confidence_desc")
    op.drop_index("ux_coin_relations_leader_follower", table_name="coin_relations")
    op.drop_table("coin_relations")
    op.drop_column("sector_metrics", "trend")
    op.drop_column("sector_metrics", "avg_volume_change_24h")
    op.drop_column("sector_metrics", "avg_price_change_24h")
    op.drop_column("coins", "sector")
