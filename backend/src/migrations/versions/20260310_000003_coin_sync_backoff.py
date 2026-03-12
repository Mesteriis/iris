"""Coin history sync backoff fields.

Revision ID: 20260310_000003
Revises: 20260310_000002
Create Date: 2026-03-10 23:55:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_000003"
down_revision: str | None = "20260310_000002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("coins", sa.Column("next_history_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("coins", sa.Column("last_history_sync_error", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("coins", "last_history_sync_error")
    op.drop_column("coins", "next_history_sync_at")
