"""canonical brief presentation artifact storage

Revision ID: 20260315_000035
Revises: 20260315_000034
Create Date: 2026-03-15 15:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260315_000035"
down_revision = "20260315_000034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_briefs",
        sa.Column("content_kind", sa.String(length=32), nullable=False, server_default="generated_text"),
    )
    op.add_column(
        "ai_briefs",
        sa.Column("content_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.execute(
        """
        UPDATE ai_briefs
        SET content_kind = 'generated_text',
            content_json = json_build_object(
                'version', 1,
                'kind', 'generated_text',
                'rendered_locale', language,
                'title', title,
                'summary', summary,
                'bullets', COALESCE(bullets_json, '[]'::json)
            )
        """
    )
    op.execute("UPDATE ai_briefs SET title = '', summary = '', bullets_json = '[]'::json")
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY brief_kind, scope_key
                    ORDER BY updated_at DESC, id DESC
                ) AS row_num
            FROM ai_briefs
        )
        DELETE FROM ai_briefs
        WHERE id IN (SELECT id FROM ranked WHERE row_num > 1)
        """
    )
    op.execute("DROP INDEX IF EXISTS ux_ai_briefs_scope_lang")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_briefs_scope "
        "ON ai_briefs (brief_kind, scope_key)"
    )
    op.alter_column("ai_briefs", "content_kind", server_default=None)
    op.alter_column("ai_briefs", "content_json", server_default=None)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_ai_briefs_scope")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_briefs_scope_lang "
        "ON ai_briefs (brief_kind, scope_key, language)"
    )
    op.drop_column("ai_briefs", "content_json")
    op.drop_column("ai_briefs", "content_kind")
