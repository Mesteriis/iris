"""Observed asset config and interval history.

Revision ID: 20260310_000002
Revises: 20260310_000001
Create Date: 2026-03-10 23:25:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_000002"
down_revision: str | None = "20260310_000001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "coins",
        sa.Column("asset_type", sa.String(length=32), nullable=False, server_default="crypto"),
    )
    op.add_column(
        "coins",
        sa.Column("theme", sa.String(length=64), nullable=False, server_default="core"),
    )
    op.add_column(
        "coins",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="default"),
    )
    op.add_column(
        "coins",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "coins",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "coins",
        sa.Column(
            "candles_config",
            sa.JSON(),
            nullable=True,
        ),
    )
    op.add_column("coins", sa.Column("last_history_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("coins", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE coins "
        "SET candles_config = json_build_array("
        "json_build_object('interval', '1h', 'retention_bars', 8760)"
        ") "
        "WHERE candles_config IS NULL",
    )
    op.alter_column("coins", "candles_config", nullable=False)

    op.add_column(
        "price_history",
        sa.Column("interval", sa.String(length=16), nullable=False, server_default="1h"),
    )
    op.create_index(
        "ux_price_history_coin_id_interval_timestamp",
        "price_history",
        ["coin_id", "interval", "timestamp"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_price_history_coin_id_interval_timestamp", table_name="price_history")
    op.drop_column("price_history", "interval")

    op.drop_column("coins", "deleted_at")
    op.drop_column("coins", "last_history_sync_at")
    op.drop_column("coins", "candles_config")
    op.drop_column("coins", "sort_order")
    op.drop_column("coins", "enabled")
    op.drop_column("coins", "source")
    op.drop_column("coins", "theme")
    op.drop_column("coins", "asset_type")
