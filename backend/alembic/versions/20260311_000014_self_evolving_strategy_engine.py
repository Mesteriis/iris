"""Add self evolving strategy engine storage.

Revision ID: 20260311_000014
Revises: 20260311_000013
Create Date: 2026-03-11 22:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000014"
down_revision: str | None = "20260311_000013"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_strategies_name"),
    )

    op.create_table(
        "strategy_rules",
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("pattern_slug", sa.String(length=96), nullable=False),
        sa.Column("regime", sa.String(length=32), nullable=False, server_default=sa.text("'*'")),
        sa.Column("sector", sa.String(length=64), nullable=False, server_default=sa.text("'*'")),
        sa.Column("cycle", sa.String(length=32), nullable=False, server_default=sa.text("'*'")),
        sa.Column("min_confidence", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("strategy_id", "pattern_slug"),
    )
    op.execute(
        "CREATE INDEX ix_strategy_rules_context "
        "ON strategy_rules (regime, sector, cycle, min_confidence DESC)"
    )

    op.create_table(
        "strategy_performance",
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("win_rate", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_return", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("sharpe_ratio", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("max_drawdown", sa.Float(53), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("strategy_id"),
    )
    op.execute(
        "CREATE INDEX ix_strategy_performance_sharpe_desc "
        "ON strategy_performance (sharpe_ratio DESC, win_rate DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_strategy_performance_sharpe_desc")
    op.drop_table("strategy_performance")
    op.execute("DROP INDEX IF EXISTS ix_strategy_rules_context")
    op.drop_table("strategy_rules")
    op.drop_table("strategies")
