"""market structure source resilience fields

Revision ID: 20260312_000027
Revises: 20260312_000026
Create Date: 2026-03-12 23:58:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_000027"
down_revision = "20260312_000026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_structure_sources",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("market_structure_sources", sa.Column("backoff_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("market_structure_sources", sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("market_structure_sources", sa.Column("quarantine_reason", sa.String(length=255), nullable=True))
    op.add_column("market_structure_sources", sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("market_structure_sources", sa.Column("last_alert_kind", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("market_structure_sources", "last_alert_kind")
    op.drop_column("market_structure_sources", "last_alerted_at")
    op.drop_column("market_structure_sources", "quarantine_reason")
    op.drop_column("market_structure_sources", "quarantined_at")
    op.drop_column("market_structure_sources", "backoff_until")
    op.drop_column("market_structure_sources", "consecutive_failures")
