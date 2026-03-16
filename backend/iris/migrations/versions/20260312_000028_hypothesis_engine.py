"""add hypothesis engine tables

Revision ID: 20260312_000028
Revises: 20260312_000027
Create Date: 2026-03-12 23:59:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_000028"
down_revision = "20260312_000027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_prompts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("vars_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_ai_prompts_name_version", "ai_prompts", ["name", "version"], unique=True)
    op.create_index(
        "ix_ai_prompts_task_active_updated_desc",
        "ai_prompts",
        ["task", "is_active", sa.text("updated_at DESC")],
        unique=False,
    )

    op.create_table(
        "ai_hypotheses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("coin_id", sa.Integer(), sa.ForeignKey("coins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timeframe", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("statement_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("confidence", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("horizon_min", sa.Integer(), nullable=False, server_default="240"),
        sa.Column("eval_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_name", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_event_type", sa.String(length=64), nullable=False),
        sa.Column("source_stream_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_ai_hypotheses_status_eval_due_at",
        "ai_hypotheses",
        ["status", "eval_due_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_hypotheses_coin_tf_created_desc",
        "ai_hypotheses",
        ["coin_id", "timeframe", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_ai_hypotheses_type_confidence_desc",
        "ai_hypotheses",
        ["type", sa.text("confidence DESC")],
        unique=False,
    )

    op.create_table(
        "ai_hypothesis_evals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hypothesis_id", sa.BigInteger(), sa.ForeignKey("ai_hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("score", sa.Float(precision=53), nullable=False, server_default="0"),
        sa.Column("details_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_ai_hypothesis_evals_hypothesis_id", "ai_hypothesis_evals", ["hypothesis_id"], unique=True)
    op.create_index(
        "ix_ai_hypothesis_evals_evaluated_desc",
        "ai_hypothesis_evals",
        [sa.text("evaluated_at DESC")],
        unique=False,
    )

    op.create_table(
        "ai_weights",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("alpha", sa.Float(precision=53), nullable=False, server_default="1"),
        sa.Column("beta", sa.Float(precision=53), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_ai_weights_scope_key", "ai_weights", ["scope", "key"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_ai_weights_scope_key", table_name="ai_weights")
    op.drop_table("ai_weights")

    op.drop_index("ix_ai_hypothesis_evals_evaluated_desc", table_name="ai_hypothesis_evals")
    op.drop_index("ux_ai_hypothesis_evals_hypothesis_id", table_name="ai_hypothesis_evals")
    op.drop_table("ai_hypothesis_evals")

    op.drop_index("ix_ai_hypotheses_type_confidence_desc", table_name="ai_hypotheses")
    op.drop_index("ix_ai_hypotheses_coin_tf_created_desc", table_name="ai_hypotheses")
    op.drop_index("ix_ai_hypotheses_status_eval_due_at", table_name="ai_hypotheses")
    op.drop_table("ai_hypotheses")

    op.drop_index("ix_ai_prompts_task_active_updated_desc", table_name="ai_prompts")
    op.drop_index("ux_ai_prompts_name_version", table_name="ai_prompts")
    op.drop_table("ai_prompts")
