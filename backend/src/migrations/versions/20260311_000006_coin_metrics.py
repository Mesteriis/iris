"""Add coin metrics table.

Revision ID: 20260311_000006
Revises: 20260311_000005
Create Date: 2026-03-11 13:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000006"
down_revision: str | None = "20260311_000005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coin_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("price_current", sa.Numeric(20, 8), nullable=True),
        sa.Column("price_change_1h", sa.Numeric(20, 8), nullable=True),
        sa.Column("price_change_24h", sa.Numeric(20, 8), nullable=True),
        sa.Column("price_change_7d", sa.Numeric(20, 8), nullable=True),
        sa.Column("volume_24h", sa.Numeric(24, 8), nullable=True),
        sa.Column("volatility", sa.Numeric(20, 8), nullable=True),
        sa.Column("market_cap", sa.Numeric(30, 2), nullable=True),
        sa.Column("trend", sa.String(length=16), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_coin_metrics_coin_id", "coin_metrics", ["coin_id"], unique=True)
    op.execute(
        sa.text(
            """
            INSERT INTO coin_metrics (coin_id, updated_at)
            SELECT coins.id, NOW()
            FROM coins
            WHERE coins.deleted_at IS NULL
            ON CONFLICT (coin_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ux_coin_metrics_coin_id", table_name="coin_metrics")
    op.drop_table("coin_metrics")
