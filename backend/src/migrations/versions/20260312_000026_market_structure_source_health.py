"""market structure source health fields

Revision ID: 20260312_000026
Revises: 20260312_000025
Create Date: 2026-03-12 23:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_000026"
down_revision = "20260312_000025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_structure_sources", sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("market_structure_sources", sa.Column("last_snapshot_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "market_structure_sources",
        sa.Column("health_status", sa.String(length=32), nullable=False, server_default=sa.text("'idle'")),
    )
    op.add_column("market_structure_sources", sa.Column("health_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE market_structure_sources SET health_status = 'disabled' WHERE enabled = false")
    op.execute("UPDATE market_structure_sources SET health_status = 'idle' WHERE enabled = true AND health_status IS NULL")


def downgrade() -> None:
    op.drop_column("market_structure_sources", "health_changed_at")
    op.drop_column("market_structure_sources", "health_status")
    op.drop_column("market_structure_sources", "last_snapshot_at")
    op.drop_column("market_structure_sources", "last_success_at")
