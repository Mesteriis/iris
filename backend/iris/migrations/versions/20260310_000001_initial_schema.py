"""Initial IRIS schema.

Revision ID: 20260310_000001
Revises:
Create Date: 2026-03-10 00:00:01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_000001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coins_symbol", "coins", ["symbol"], unique=True)

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coin_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("volume", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.ForeignKeyConstraint(["coin_id"], ["coins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_price_history_coin_id_timestamp",
        "price_history",
        ["coin_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_price_history_coin_id_timestamp", table_name="price_history")
    op.drop_table("price_history")
    op.drop_index("ix_coins_symbol", table_name="coins")
    op.drop_table("coins")
