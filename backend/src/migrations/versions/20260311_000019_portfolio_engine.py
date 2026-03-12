"""portfolio engine

Revision ID: 20260311_000019
Revises: 20260311_000018
Create Date: 2026-03-11 18:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_000019"
down_revision = "20260311_000018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coins", sa.Column("auto_watch_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("coins", sa.Column("auto_watch_source", sa.String(length=32), nullable=True))
    op.create_table(
        "exchange_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("exchange_name", sa.String(length=32), nullable=False),
        sa.Column("account_name", sa.String(length=64), nullable=False),
        sa.Column("api_key", sa.String(length=255), nullable=False),
        sa.Column("api_secret", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_exchange_accounts_exchange_enabled", "exchange_accounts", ["exchange_name", "enabled"])
    op.create_table(
        "portfolio_state",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("total_capital", sa.Float(precision=53), nullable=False, server_default="100000"),
        sa.Column("allocated_capital", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("available_capital", sa.Float(precision=53), nullable=False, server_default="100000"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "portfolio_positions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exchange_account_id", sa.Integer(), sa.ForeignKey("exchange_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_exchange", sa.String(length=32), nullable=True),
        sa.Column("position_type", sa.String(length=16), nullable=False, server_default="spot"),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("entry_price", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("position_size", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("position_value", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("stop_loss", sa.Float(precision=53), nullable=True),
        sa.Column("take_profit", sa.Float(precision=53), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_portfolio_positions_coin_tf_status", "portfolio_positions", ["coin_id", "timeframe", "status"])
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_positions_value_desc ON portfolio_positions (position_value DESC)")
    op.create_table(
        "portfolio_actions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("size", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("decision_id", sa.BigInteger(), sa.ForeignKey("market_decisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_actions_created_desc ON portfolio_actions (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_actions_coin_created_desc ON portfolio_actions (coin_id, created_at DESC)")
    op.create_table(
        "portfolio_balances",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("exchange_account_id", sa.Integer(), sa.ForeignKey("exchange_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("balance", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("value_usd", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_portfolio_balances_account_symbol", "portfolio_balances", ["exchange_account_id", "symbol"], unique=True)
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_balances_value_desc ON portfolio_balances (value_usd DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_portfolio_balances_value_desc")
    op.drop_index("ux_portfolio_balances_account_symbol", table_name="portfolio_balances")
    op.drop_table("portfolio_balances")
    op.execute("DROP INDEX IF EXISTS ix_portfolio_actions_coin_created_desc")
    op.execute("DROP INDEX IF EXISTS ix_portfolio_actions_created_desc")
    op.drop_table("portfolio_actions")
    op.execute("DROP INDEX IF EXISTS ix_portfolio_positions_value_desc")
    op.drop_index("ix_portfolio_positions_coin_tf_status", table_name="portfolio_positions")
    op.drop_table("portfolio_positions")
    op.drop_table("portfolio_state")
    op.drop_index("ix_exchange_accounts_exchange_enabled", table_name="exchange_accounts")
    op.drop_table("exchange_accounts")
    op.drop_column("coins", "auto_watch_source")
    op.drop_column("coins", "auto_watch_enabled")
