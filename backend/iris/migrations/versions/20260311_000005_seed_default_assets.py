"""Seed default observed assets.

Revision ID: 20260311_000005
Revises: 20260310_000004
Create Date: 2026-03-11 00:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260311_000005"
down_revision: str | None = "20260310_000004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _candles(*items: tuple[str, int]) -> list[dict[str, int | str]]:
    return [
        {"interval": interval, "retention_bars": retention_bars}
        for interval, retention_bars in items
    ]


DEFAULT_ASSETS: list[dict[str, object]] = [
    {
        "symbol": "BTCUSD",
        "name": "Bitcoin",
        "asset_type": "crypto",
        "theme": "core",
        "source": "default",
        "enabled": True,
        "sort_order": 10,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 3650)),
    },
    {
        "symbol": "ETHUSD",
        "name": "Ethereum",
        "asset_type": "crypto",
        "theme": "core",
        "source": "default",
        "enabled": True,
        "sort_order": 20,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 3650)),
    },
    {
        "symbol": "SOLUSD",
        "name": "Solana",
        "asset_type": "crypto",
        "theme": "beta",
        "source": "default",
        "enabled": True,
        "sort_order": 25,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 3650)),
    },
    {
        "symbol": "DOGEUSD",
        "name": "Dogecoin",
        "asset_type": "crypto",
        "theme": "beta",
        "source": "default",
        "enabled": True,
        "sort_order": 27,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 3650)),
    },
    {
        "symbol": "ETHBTC",
        "name": "Ethereum / Bitcoin",
        "asset_type": "crypto",
        "theme": "relative-strength",
        "source": "default",
        "enabled": True,
        "sort_order": 28,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 3650)),
    },
    {
        "symbol": "FETUSD",
        "name": "Fetch.ai",
        "asset_type": "crypto",
        "theme": "ai",
        "source": "default",
        "enabled": True,
        "sort_order": 30,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "RENDERUSD",
        "name": "Render",
        "asset_type": "crypto",
        "theme": "ai",
        "source": "default",
        "enabled": True,
        "sort_order": 40,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "TAOUSD",
        "name": "Bittensor",
        "asset_type": "crypto",
        "theme": "ai",
        "source": "default",
        "enabled": True,
        "sort_order": 50,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "AKTUSD",
        "name": "Akash Network",
        "asset_type": "crypto",
        "theme": "ai",
        "source": "default",
        "enabled": True,
        "sort_order": 60,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "EURUSD",
        "name": "Euro / US Dollar",
        "asset_type": "forex",
        "theme": "fx",
        "source": "default",
        "enabled": True,
        "sort_order": 70,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "DXY",
        "name": "US Dollar Index",
        "asset_type": "index",
        "theme": "fx",
        "source": "default",
        "enabled": True,
        "sort_order": 80,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "DJI",
        "name": "Dow Jones Industrial Average",
        "asset_type": "index",
        "theme": "macro",
        "source": "default",
        "enabled": True,
        "sort_order": 85,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "GSPC",
        "name": "S&P 500",
        "asset_type": "index",
        "theme": "macro",
        "source": "default",
        "enabled": True,
        "sort_order": 86,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "NDX",
        "name": "Nasdaq 100",
        "asset_type": "index",
        "theme": "macro",
        "source": "default",
        "enabled": True,
        "sort_order": 87,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "VIX",
        "name": "CBOE Volatility Index",
        "asset_type": "index",
        "theme": "volatility",
        "source": "default",
        "enabled": True,
        "sort_order": 88,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "TNX",
        "name": "US 10Y Treasury Yield",
        "asset_type": "index",
        "theme": "rates",
        "source": "default",
        "enabled": True,
        "sort_order": 89,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "USDRUB",
        "name": "US Dollar / Russian Ruble",
        "asset_type": "forex",
        "theme": "fx",
        "source": "default",
        "enabled": True,
        "sort_order": 90,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "USDCNY",
        "name": "US Dollar / Chinese Yuan",
        "asset_type": "forex",
        "theme": "fx",
        "source": "default",
        "enabled": True,
        "sort_order": 100,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "IMOEX",
        "name": "MOEX Russia Index",
        "asset_type": "index",
        "theme": "russia",
        "source": "moex",
        "enabled": True,
        "sort_order": 102,
        "candles_config": _candles(("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "RTSI",
        "name": "RTS Index",
        "asset_type": "index",
        "theme": "russia",
        "source": "moex",
        "enabled": True,
        "sort_order": 104,
        "candles_config": _candles(("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "GDAXI",
        "name": "DAX 40",
        "asset_type": "index",
        "theme": "europe",
        "source": "default",
        "enabled": True,
        "sort_order": 106,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "STOXX50E",
        "name": "Euro Stoxx 50",
        "asset_type": "index",
        "theme": "europe",
        "source": "default",
        "enabled": True,
        "sort_order": 108,
        "candles_config": _candles(("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "XAUUSD",
        "name": "Gold",
        "asset_type": "metal",
        "theme": "hard-assets",
        "source": "default",
        "enabled": True,
        "sort_order": 110,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
    {
        "symbol": "XAGUSD",
        "name": "Silver",
        "asset_type": "metal",
        "theme": "hard-assets",
        "source": "default",
        "enabled": True,
        "sort_order": 120,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "NATGASUSD",
        "name": "Natural Gas",
        "asset_type": "energy",
        "theme": "energy",
        "source": "default",
        "enabled": True,
        "sort_order": 130,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "BRENTUSD",
        "name": "Brent Crude",
        "asset_type": "energy",
        "theme": "energy",
        "source": "default",
        "enabled": True,
        "sort_order": 140,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "WTIUSD",
        "name": "WTI Crude",
        "asset_type": "energy",
        "theme": "energy",
        "source": "default",
        "enabled": True,
        "sort_order": 150,
        "candles_config": _candles(("1d", 1095)),
    },
    {
        "symbol": "URALSUSD",
        "name": "Urals Crude",
        "asset_type": "energy",
        "theme": "energy",
        "source": "default",
        "enabled": False,
        "sort_order": 160,
        "candles_config": _candles(("15m", 5760), ("1h", 8760), ("4h", 4380), ("1d", 1095)),
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    coins = sa.table(
        "coins",
        sa.column("symbol", sa.String(length=16)),
        sa.column("name", sa.String(length=120)),
        sa.column("asset_type", sa.String(length=32)),
        sa.column("theme", sa.String(length=64)),
        sa.column("source", sa.String(length=32)),
        sa.column("enabled", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("candles_config", sa.JSON()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )

    insert_stmt = postgresql.insert(coins).values(DEFAULT_ASSETS)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["symbol"],
        set_={
            "name": insert_stmt.excluded.name,
            "asset_type": insert_stmt.excluded.asset_type,
            "theme": insert_stmt.excluded.theme,
            "source": insert_stmt.excluded.source,
            "enabled": insert_stmt.excluded.enabled,
            "sort_order": insert_stmt.excluded.sort_order,
            "candles_config": insert_stmt.excluded.candles_config,
        },
        where=coins.c.deleted_at.is_(None),
    )
    bind.execute(upsert_stmt)


def downgrade() -> None:
    bind = op.get_bind()
    symbols = [asset["symbol"] for asset in DEFAULT_ASSETS]
    coins = sa.table("coins", sa.column("symbol", sa.String(length=16)))
    bind.execute(sa.delete(coins).where(coins.c.symbol.in_(symbols)))
