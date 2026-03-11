"""Unify history storage into candles.

Revision ID: 20260311_000008
Revises: 20260311_000007
Create Date: 2026-03-11 02:35:00
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260311_000008"
down_revision: str | None = "20260311_000007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE coins
        SET history_backfill_completed_at = NULL,
            last_history_sync_at = NULL,
            next_history_sync_at = NULL,
            last_history_sync_error = NULL
        WHERE deleted_at IS NULL
          AND enabled IS TRUE
        """
    )
    op.execute("DROP INDEX IF EXISTS ux_price_history_coin_id_interval_timestamp")
    op.execute("DROP INDEX IF EXISTS ix_price_history_coin_id_timestamp")
    op.execute("DROP TABLE IF EXISTS price_history")


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported after consolidating history storage into candles.")
