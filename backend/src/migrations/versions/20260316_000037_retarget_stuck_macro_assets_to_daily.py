"""Retarget stuck macro assets to supported daily history.

Revision ID: 20260316_000037
Revises: 20260315_000036
Create Date: 2026-03-16 02:15:00
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260316_000037"
down_revision: str | None = "20260315_000036"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


DAILY_SYMBOLS: tuple[str, ...] = ("DJI", "GSPC", "GDAXI", "XAGUSD")
DAILY_CANDLES = json.dumps([{"interval": "1d", "retention_bars": 1095}])
INDEX_INTRADAY_CANDLES = json.dumps(
    [
        {"interval": "1h", "retention_bars": 8760},
        {"interval": "4h", "retention_bars": 4380},
        {"interval": "1d", "retention_bars": 1095},
    ]
)
METAL_INTRADAY_CANDLES = json.dumps(
    [
        {"interval": "15m", "retention_bars": 20160},
        {"interval": "1h", "retention_bars": 8760},
        {"interval": "4h", "retention_bars": 4380},
        {"interval": "1d", "retention_bars": 1095},
    ]
)


def _reset_sync_state_sql() -> str:
    return """
        history_backfill_completed_at = NULL,
        last_history_sync_at = NULL,
        next_history_sync_at = NULL,
        last_history_sync_error = NULL
    """


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"""
            UPDATE coins
            SET source = 'default',
                candles_config = CAST(:candles_config AS JSON),
                {_reset_sync_state_sql()}
            WHERE symbol = ANY(:symbols)
              AND deleted_at IS NULL
            """
        ),
        {
            "symbols": list(DAILY_SYMBOLS),
            "candles_config": DAILY_CANDLES,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"""
            UPDATE coins
            SET source = 'default',
                candles_config = CAST(:candles_config AS JSON),
                {_reset_sync_state_sql()}
            WHERE symbol = ANY(:symbols)
              AND deleted_at IS NULL
            """
        ),
        {
            "symbols": ["DJI", "GSPC", "GDAXI"],
            "candles_config": INDEX_INTRADAY_CANDLES,
        },
    )
    bind.execute(
        sa.text(
            f"""
            UPDATE coins
            SET source = 'default',
                candles_config = CAST(:candles_config AS JSON),
                {_reset_sync_state_sql()}
            WHERE symbol = 'XAGUSD'
              AND deleted_at IS NULL
            """
        ),
        {
            "candles_config": METAL_INTRADAY_CANDLES,
        },
    )
