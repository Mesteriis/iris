"""Add smart market scheduling fields to coin metrics.

Revision ID: 20260311_000016
Revises: 20260311_000015
Create Date: 2026-03-11 16:25:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_000016"
down_revision: str | None = "20260311_000015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("coin_metrics", sa.Column("activity_score", sa.Float(53), nullable=True))
    op.add_column("coin_metrics", sa.Column("activity_bucket", sa.String(length=16), nullable=True))
    op.add_column("coin_metrics", sa.Column("analysis_priority", sa.Integer(), nullable=True))
    op.add_column("coin_metrics", sa.Column("last_analysis_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_coin_metrics_activity_score_desc "
        "ON coin_metrics (activity_score DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_coin_metrics_activity_bucket_priority "
        "ON coin_metrics (activity_bucket, analysis_priority DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_coin_metrics_activity_bucket_priority")
    op.execute("DROP INDEX IF EXISTS ix_coin_metrics_activity_score_desc")
    op.drop_column("coin_metrics", "last_analysis_at")
    op.drop_column("coin_metrics", "analysis_priority")
    op.drop_column("coin_metrics", "activity_bucket")
    op.drop_column("coin_metrics", "activity_score")
