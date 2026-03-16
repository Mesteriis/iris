"""Retarget stuck macro assets to supported daily history.

Revision ID: 20260316_000037
Revises: 20260315_000036
Create Date: 2026-03-16 02:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260316_000037"
down_revision: str | None = "20260315_000036"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


DAILY_SYMBOLS: tuple[str, ...] = ("DJI", "GSPC", "GDAXI", "XAGUSD")
DAILY_CANDLES = [{"interval": "1d", "retention_bars": 1095}]
INDEX_INTRADAY_CANDLES = [
    {"interval": "1h", "retention_bars": 8760},
    {"interval": "4h", "retention_bars": 4380},
    {"interval": "1d", "retention_bars": 1095},
]
METAL_INTRADAY_CANDLES = [
    {"interval": "15m", "retention_bars": 20160},
    {"interval": "1h", "retention_bars": 8760},
    {"interval": "4h", "retention_bars": 4380},
    {"interval": "1d", "retention_bars": 1095},
]
COINS = sa.table(
    "coins",
    sa.column("symbol", sa.String()),
    sa.column("deleted_at", sa.DateTime(timezone=True)),
    sa.column("source", sa.String()),
    sa.column("candles_config", sa.JSON()),
    sa.column("history_backfill_completed_at", sa.DateTime(timezone=True)),
    sa.column("last_history_sync_at", sa.DateTime(timezone=True)),
    sa.column("next_history_sync_at", sa.DateTime(timezone=True)),
    sa.column("last_history_sync_error", sa.Text()),
)


def _reset_sync_state_values() -> dict[str, None]:
    return {
        "history_backfill_completed_at": None,
        "last_history_sync_at": None,
        "next_history_sync_at": None,
        "last_history_sync_error": None,
    }


def _retarget_symbols(symbols: Sequence[str], *, candles_config: list[dict[str, object]]) -> None:
    op.execute(
        sa.update(COINS)
        .where(COINS.c.symbol.in_(list(symbols)), COINS.c.deleted_at.is_(None))
        .values(source="default", candles_config=candles_config, **_reset_sync_state_values())
    )


def _retarget_symbol(symbol: str, *, candles_config: list[dict[str, object]]) -> None:
    op.execute(
        sa.update(COINS)
        .where(COINS.c.symbol == symbol, COINS.c.deleted_at.is_(None))
        .values(source="default", candles_config=candles_config, **_reset_sync_state_values())
    )


def upgrade() -> None:
    _retarget_symbols(DAILY_SYMBOLS, candles_config=DAILY_CANDLES)


def downgrade() -> None:
    _retarget_symbols(("DJI", "GSPC", "GDAXI"), candles_config=INDEX_INTRADAY_CANDLES)
    _retarget_symbol("XAGUSD", candles_config=METAL_INTRADAY_CANDLES)
