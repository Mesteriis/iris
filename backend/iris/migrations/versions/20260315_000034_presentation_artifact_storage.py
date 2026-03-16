"""canonical presentation artifact storage for notifications and explanations

Revision ID: 20260315_000034
Revises: 20260315_000033
Create Date: 2026-03-15 14:20:00.000000
"""


import sqlalchemy as sa
from alembic import op

revision = "20260315_000034"
down_revision = "20260315_000033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_notifications",
        sa.Column("content_kind", sa.String(length=32), nullable=False, server_default="generated_text"),
    )
    op.add_column(
        "ai_notifications",
        sa.Column("content_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.add_column(
        "ai_explanations",
        sa.Column("content_kind", sa.String(length=32), nullable=False, server_default="generated_text"),
    )
    op.add_column(
        "ai_explanations",
        sa.Column("content_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )

    op.execute(
        """
        UPDATE ai_notifications
        SET content_kind = CASE
                WHEN COALESCE(context_json -> 'localization' ->> 'strategy', '') = 'descriptor_render'
                    THEN 'descriptor_bundle'
                ELSE 'generated_text'
            END,
            content_json = CASE
                WHEN COALESCE(context_json -> 'localization' ->> 'strategy', '') = 'descriptor_render'
                    THEN json_build_object(
                        'version', 1,
                        'kind', 'descriptor_bundle',
                        'title', context_json -> 'localization' -> 'title',
                        'message', context_json -> 'localization' -> 'message'
                    )
                ELSE json_build_object(
                    'version', 1,
                    'kind', 'generated_text',
                    'rendered_locale', language,
                    'title', title,
                    'message', message
                )
            END
        """
    )
    op.execute("UPDATE ai_notifications SET title = '', message = ''")
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY source_event_type, source_event_id
                    ORDER BY
                        CASE WHEN content_kind = 'descriptor_bundle' THEN 0 ELSE 1 END,
                        updated_at DESC,
                        id DESC
                ) AS row_num
            FROM ai_notifications
        )
        DELETE FROM ai_notifications
        WHERE id IN (SELECT id FROM ranked WHERE row_num > 1)
        """
    )
    op.execute("DROP INDEX IF EXISTS ux_ai_notifications_source_event_lang")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_notifications_source_event "
        "ON ai_notifications (source_event_type, source_event_id)"
    )

    op.execute(
        """
        UPDATE ai_explanations
        SET content_kind = CASE
                WHEN COALESCE(context_json -> 'localization' ->> 'strategy', '') = 'descriptor_render'
                    THEN 'descriptor_bundle'
                ELSE 'generated_text'
            END,
            content_json = CASE
                WHEN COALESCE(context_json -> 'localization' ->> 'strategy', '') = 'descriptor_render'
                    THEN json_build_object(
                        'version', 1,
                        'kind', 'descriptor_bundle',
                        'title', context_json -> 'localization' -> 'title',
                        'explanation', context_json -> 'localization' -> 'explanation',
                        'bullets', COALESCE(context_json -> 'localization' -> 'bullets', '[]'::json)
                    )
                ELSE json_build_object(
                    'version', 1,
                    'kind', 'generated_text',
                    'rendered_locale', language,
                    'title', title,
                    'explanation', explanation,
                    'bullets', COALESCE(bullets_json, '[]'::json)
                )
            END
        """
    )
    op.execute("UPDATE ai_explanations SET title = '', explanation = '', bullets_json = '[]'::json")
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY explain_kind, subject_id
                    ORDER BY
                        CASE WHEN content_kind = 'descriptor_bundle' THEN 0 ELSE 1 END,
                        updated_at DESC,
                        id DESC
                ) AS row_num
            FROM ai_explanations
        )
        DELETE FROM ai_explanations
        WHERE id IN (SELECT id FROM ranked WHERE row_num > 1)
        """
    )
    op.execute("DROP INDEX IF EXISTS ux_ai_explanations_subject_lang")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_explanations_subject "
        "ON ai_explanations (explain_kind, subject_id)"
    )

    op.alter_column("ai_notifications", "content_kind", server_default=None)
    op.alter_column("ai_notifications", "content_json", server_default=None)
    op.alter_column("ai_explanations", "content_kind", server_default=None)
    op.alter_column("ai_explanations", "content_json", server_default=None)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_ai_explanations_subject")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_explanations_subject_lang "
        "ON ai_explanations (explain_kind, subject_id, language)"
    )
    op.execute("DROP INDEX IF EXISTS ux_ai_notifications_source_event")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_notifications_source_event_lang "
        "ON ai_notifications (source_event_type, source_event_id, language)"
    )
    op.drop_column("ai_explanations", "content_json")
    op.drop_column("ai_explanations", "content_kind")
    op.drop_column("ai_notifications", "content_json")
    op.drop_column("ai_notifications", "content_kind")
