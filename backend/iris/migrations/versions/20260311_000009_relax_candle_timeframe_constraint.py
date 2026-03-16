"""Allow multi-timeframe candles in canonical history table.

Revision ID: 20260311_000009
Revises: 20260311_000008
Create Date: 2026-03-11 21:45:00
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260311_000009"
down_revision: str | None = "20260311_000008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_candles_timeframe_15", "candles", type_="check")


def downgrade() -> None:
    op.create_check_constraint("ck_candles_timeframe_15", "candles", "timeframe = 15")
