"""Retarget daily-resilience seed assets to daily-only history.

Revision ID: 20260316_000038
Revises: 20260316_000037
Create Date: 2026-03-16 08:00:00
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260316_000038"
down_revision: str | None = "20260316_000037"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


DAILY_RESILIENCE_SYMBOLS: tuple[str, ...] = (
    "DXY",
    "NDX",
    "VIX",
    "TNX",
    "NATGASUSD",
    "BRENTUSD",
    "WTIUSD",
)
DAILY_CANDLES = json.dumps([{"interval": "1d", "retention_bars": 1095}])
INDEX_INTRADAY_CANDLES = json.dumps(
    [
        {"interval": "1h", "retention_bars": 8760},
        {"interval": "4h", "retention_bars": 4380},
        {"interval": "1d", "retention_bars": 1095},
    ]
)
ENERGY_INTRADAY_CANDLES = json.dumps(
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
            "symbols": list(DAILY_RESILIENCE_SYMBOLS),
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
            "symbols": ["DXY", "NDX", "VIX", "TNX"],
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
            WHERE symbol = ANY(:symbols)
              AND deleted_at IS NULL
            """
        ),
        {
            "symbols": ["NATGASUSD", "BRENTUSD", "WTIUSD"],
            "candles_config": ENERGY_INTRADAY_CANDLES,
        },
    )
