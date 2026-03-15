"""drop legacy localized text columns from presentation artifacts

Revision ID: 20260315_000036
Revises: 20260315_000035
Create Date: 2026-03-15 17:40:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260315_000036"
down_revision = "20260315_000035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("ai_notifications", "language")
    op.drop_column("ai_notifications", "message")
    op.drop_column("ai_notifications", "title")

    op.drop_column("ai_explanations", "language")
    op.drop_column("ai_explanations", "bullets_json")
    op.drop_column("ai_explanations", "explanation")
    op.drop_column("ai_explanations", "title")

    op.drop_column("ai_briefs", "language")
    op.drop_column("ai_briefs", "bullets_json")
    op.drop_column("ai_briefs", "summary")
    op.drop_column("ai_briefs", "title")


def downgrade() -> None:
    op.add_column("ai_briefs", sa.Column("title", sa.String(length=160), nullable=False, server_default=""))
    op.add_column("ai_briefs", sa.Column("summary", sa.Text(), nullable=False, server_default=""))
    op.add_column("ai_briefs", sa.Column("bullets_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column("ai_briefs", sa.Column("language", sa.String(length=16), nullable=False, server_default="en"))
    op.execute(
        """
        UPDATE ai_briefs
        SET language = COALESCE(content_json ->> 'rendered_locale', 'en'),
            title = CASE
                WHEN content_kind = 'generated_text' THEN COALESCE(content_json ->> 'title', '')
                ELSE ''
            END,
            summary = CASE
                WHEN content_kind = 'generated_text' THEN COALESCE(content_json ->> 'summary', '')
                ELSE ''
            END,
            bullets_json = CASE
                WHEN content_kind = 'generated_text' THEN COALESCE(content_json -> 'bullets', '[]'::json)
                ELSE '[]'::json
            END
        """
    )
    op.alter_column("ai_briefs", "language", server_default=None)
    op.alter_column("ai_briefs", "bullets_json", server_default=None)
    op.alter_column("ai_briefs", "summary", server_default=None)
    op.alter_column("ai_briefs", "title", server_default=None)

    op.add_column("ai_explanations", sa.Column("title", sa.String(length=160), nullable=False, server_default=""))
    op.add_column("ai_explanations", sa.Column("explanation", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "ai_explanations",
        sa.Column("bullets_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column("ai_explanations", sa.Column("language", sa.String(length=16), nullable=False, server_default="en"))
    op.execute(
        """
        UPDATE ai_explanations
        SET language = COALESCE(content_json ->> 'rendered_locale', 'en'),
            title = CASE
                WHEN content_kind = 'generated_text' THEN COALESCE(content_json ->> 'title', '')
                ELSE ''
            END,
            explanation = CASE
                WHEN content_kind = 'generated_text' THEN COALESCE(content_json ->> 'explanation', '')
                ELSE ''
            END,
            bullets_json = CASE
                WHEN content_kind = 'generated_text' THEN COALESCE(content_json -> 'bullets', '[]'::json)
                ELSE '[]'::json
            END
        """
    )
    op.alter_column("ai_explanations", "language", server_default=None)
    op.alter_column("ai_explanations", "bullets_json", server_default=None)
    op.alter_column("ai_explanations", "explanation", server_default=None)
    op.alter_column("ai_explanations", "title", server_default=None)

    op.add_column("ai_notifications", sa.Column("title", sa.String(length=160), nullable=False, server_default=""))
    op.add_column("ai_notifications", sa.Column("message", sa.Text(), nullable=False, server_default=""))
    op.add_column("ai_notifications", sa.Column("language", sa.String(length=16), nullable=False, server_default="en"))
    op.execute(
        """
        UPDATE ai_notifications
        SET language = COALESCE(content_json ->> 'rendered_locale', 'en'),
            title = CASE
                WHEN content_kind = 'generated_text' THEN COALESCE(content_json ->> 'title', '')
                ELSE ''
            END,
            message = CASE
                WHEN content_kind = 'generated_text' THEN COALESCE(content_json ->> 'message', '')
                ELSE ''
            END
        """
    )
    op.alter_column("ai_notifications", "language", server_default=None)
    op.alter_column("ai_notifications", "message", server_default=None)
    op.alter_column("ai_notifications", "title", server_default=None)
