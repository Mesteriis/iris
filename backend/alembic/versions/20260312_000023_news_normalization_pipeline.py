"""news normalization pipeline

Revision ID: 20260312_000023
Revises: 20260312_000022
Create Date: 2026-03-12 17:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_000023"
down_revision = "20260312_000022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_items",
        sa.Column("normalization_status", sa.String(length=24), nullable=False, server_default="pending"),
    )
    op.add_column(
        "news_items",
        sa.Column("normalized_payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.add_column("news_items", sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("news_items", sa.Column("sentiment_score", sa.Float(), nullable=True))
    op.add_column("news_items", sa.Column("relevance_score", sa.Float(), nullable=True))
    op.execute("ALTER TABLE news_items ALTER COLUMN normalization_status DROP DEFAULT")
    op.execute("ALTER TABLE news_items ALTER COLUMN normalized_payload_json DROP DEFAULT")

    op.create_table(
        "news_item_links",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("news_item_id", sa.BigInteger(), sa.ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coin_symbol", sa.String(length=16), nullable=False),
        sa.Column("matched_symbol", sa.String(length=32), nullable=False),
        sa.Column("link_type", sa.String(length=24), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_news_item_links_item_coin "
        "ON news_item_links (news_item_id, coin_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_news_item_links_coin_confidence_desc "
        "ON news_item_links (coin_id, confidence DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_news_item_links_coin_confidence_desc")
    op.execute("DROP INDEX IF EXISTS ux_news_item_links_item_coin")
    op.drop_table("news_item_links")
    op.drop_column("news_items", "relevance_score")
    op.drop_column("news_items", "sentiment_score")
    op.drop_column("news_items", "normalized_at")
    op.drop_column("news_items", "normalized_payload_json")
    op.drop_column("news_items", "normalization_status")
