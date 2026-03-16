"""Persist per-timeframe market regime details in coin metrics.

Revision ID: 20260311_000011
Revises: 20260311_000010
Create Date: 2026-03-11 18:05:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000011"
down_revision: str | None = "20260311_000010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("coin_metrics", sa.Column("market_regime_details", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("coin_metrics", "market_regime_details")
