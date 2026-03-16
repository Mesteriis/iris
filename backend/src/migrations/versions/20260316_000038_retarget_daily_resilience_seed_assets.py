"""Retarget daily-resilience seed assets to daily-only history.

Revision ID: 20260316_000038
Revises: 20260316_000037
Create Date: 2026-03-16 08:00:00
"""

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
DAILY_CANDLES = [{"interval": "1d", "retention_bars": 1095}]
INDEX_INTRADAY_CANDLES = [
    {"interval": "1h", "retention_bars": 8760},
    {"interval": "4h", "retention_bars": 4380},
    {"interval": "1d", "retention_bars": 1095},
]
ENERGY_INTRADAY_CANDLES = [
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


def upgrade() -> None:
    _retarget_symbols(DAILY_RESILIENCE_SYMBOLS, candles_config=DAILY_CANDLES)


def downgrade() -> None:
    _retarget_symbols(("DXY", "NDX", "VIX", "TNX"), candles_config=INDEX_INTRADAY_CANDLES)
    _retarget_symbols(("NATGASUSD", "BRENTUSD", "WTIUSD"), candles_config=ENERGY_INTRADAY_CANDLES)
