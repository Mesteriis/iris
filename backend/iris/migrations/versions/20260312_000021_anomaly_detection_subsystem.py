"""anomaly detection subsystem

Revision ID: 20260312_000021
Revises: 20260311_000020
Create Date: 2026-03-12 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_000021"
down_revision = "20260311_000020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_anomalies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("anomaly_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_regime", sa.String(length=32), nullable=True),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_anomalies_coin_tf_type_detected_desc "
        "ON market_anomalies (coin_id, timeframe, anomaly_type, detected_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_anomalies_status_detected_desc "
        "ON market_anomalies (status, detected_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_anomalies_severity_score_desc "
        "ON market_anomalies (severity, score DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_market_anomalies_severity_score_desc")
    op.execute("DROP INDEX IF EXISTS ix_market_anomalies_status_detected_desc")
    op.execute("DROP INDEX IF EXISTS ix_market_anomalies_coin_tf_type_detected_desc")
    op.drop_table("market_anomalies")
