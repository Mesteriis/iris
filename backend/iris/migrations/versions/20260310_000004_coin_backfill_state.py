"""Coin backfill completion state.

Revision ID: 20260310_000004
Revises: 20260310_000003
Create Date: 2026-03-10 23:59:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_000004"
down_revision: str | None = "20260310_000003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("coins", sa.Column("history_backfill_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("coins", "history_backfill_completed_at")
