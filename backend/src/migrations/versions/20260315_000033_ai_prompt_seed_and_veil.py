"""seed ai prompts and add veil lock

Revision ID: 20260315_000033
Revises: 20260314_000032
Create Date: 2026-03-15 10:33:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260315_000033"
down_revision = "20260314_000032"
branch_labels = None
depends_on = None

_HYPOTHESIS_BASE_TEMPLATE = (
    "You are IRIS hypothesis engine. Produce one testable market hypothesis as JSON only. "
    "Focus on the triggering event, specify direction, horizon, target move, summary, and assets."
)

_NOTIFICATION_BASE_TEMPLATE = """
You produce a short investor-facing notification from a canonical IRIS event.

Rules:
- Return valid JSON only.
- Keep the title short and specific.
- Keep the message concise, factual and grounded in the provided canonical fields.
- Do not invent prices, causes or recommendations that are absent from the context.
- Mention the symbol when it is available.
- Use the effective language exactly as requested by the execution contract.
- Map urgency and severity to the business importance of the event.
""".strip()

_BRIEF_BASE_TEMPLATE = """
You produce a stored analytical brief from deterministic IRIS context.

Rules:
- Return valid JSON only.
- Ground every sentence in the provided canonical snapshot.
- Do not invent prices, causes, catalysts or recommendations that are absent from the context.
- Use the effective language exactly as required by the execution contract.
- Keep the title concise.
- Keep the summary compact and factual.
- Bullets must be short, concrete and non-duplicative.
""".strip()

_EXPLAIN_BASE_TEMPLATE = """
You produce a bounded investor-facing explanation from deterministic IRIS context.

Rules:
- Return valid JSON only.
- Do not invent missing facts, prices, catalysts or guarantees.
- Keep the explanation grounded in canonical machine fields.
- Use the effective language exactly as required by the execution contract.
- Explain what the signal or decision means, not what the user must do.
- Keep bullets short and factual.
""".strip()


def _seed_prompt_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "name": "hypothesis.default",
            "task": "hypothesis_generation",
            "version": 1,
            "veil_lifted": False,
            "is_active": True,
            "template": _HYPOTHESIS_BASE_TEMPLATE,
            "vars_json": {"horizon_min": 240, "target_move": 0.015, "style_profile": "default"},
        }
    ]
    rows.extend(
        [
            {
                "name": f"hypothesis.{event_type}",
                "task": "hypothesis_generation",
                "version": 1,
                "veil_lifted": False,
                "is_active": True,
                "template": f"{_HYPOTHESIS_BASE_TEMPLATE} Triggering event type: {event_type}.",
                "vars_json": {"horizon_min": 240, "target_move": 0.015, "style_profile": "default"},
            }
            for event_type in (
                "signal_created",
                "anomaly_detected",
                "decision_generated",
                "market_regime_changed",
                "portfolio_position_changed",
                "portfolio_balance_updated",
            )
        ]
    )

    notification_guidance = {
        "notification.default": "Keep the narration grounded in the canonical event.",
        "notification.signal_created": "Explain the signal in plain language without pretending it is a confirmed outcome.",
        "notification.anomaly_detected": "Treat anomalies as cautionary events and avoid overclaiming certainty.",
        "notification.decision_generated": "Present the decision as a generated action candidate, not as executed trade confirmation.",
        "notification.market_regime_changed": "Emphasize the regime transition and its practical meaning for a passive investor.",
        "notification.portfolio_position_changed": "Describe the portfolio position change as an observed state update.",
        "notification.portfolio_balance_updated": "Describe the balance update as a sync result and keep the wording operational.",
    }
    for name, suffix in notification_guidance.items():
        rows.append(
            {
                "name": name,
                "task": "notification_humanize",
                "version": 1,
                "veil_lifted": False,
                "is_active": True,
                "template": f"{_NOTIFICATION_BASE_TEMPLATE}\n\nEvent-specific guidance:\n- {suffix}",
                "vars_json": {
                    "style_profile": "calm_investor_alert",
                    "max_title_chars": 96,
                    "max_message_chars": 280,
                },
            }
        )

    brief_guidance = {
        "brief.market": (
            "Summarize the current cross-symbol market snapshot without pretending it is a trading instruction.",
            "market_snapshot_brief",
        ),
        "brief.symbol": (
            "Summarize the symbol snapshot across available timeframes and keep the wording investor-facing, not trader-hype.",
            "symbol_snapshot_brief",
        ),
        "brief.portfolio": (
            "Summarize allocation, risk concentration and open-position posture without presenting the text as an execution confirmation.",
            "portfolio_snapshot_brief",
        ),
    }
    for name, (suffix, style_profile) in brief_guidance.items():
        rows.append(
            {
                "name": name,
                "task": "brief_generate",
                "version": 1,
                "veil_lifted": False,
                "is_active": True,
                "template": f"{_BRIEF_BASE_TEMPLATE}\n\nKind-specific guidance:\n- {suffix}",
                "vars_json": {
                    "style_profile": style_profile,
                    "max_title_chars": 120,
                    "max_summary_chars": 640,
                    "max_bullets": 5,
                },
            }
        )

    explain_guidance = {
        "explain.signal": (
            "Explain the meaning of the specific signal and its confidence context without pretending it is an executed action.",
            "signal_explanation",
        ),
        "explain.decision": (
            "Explain the specific investment decision using its canonical reason and scoring context without turning it into personalized advice.",
            "decision_explanation",
        ),
    }
    for name, (suffix, style_profile) in explain_guidance.items():
        rows.append(
            {
                "name": name,
                "task": "explain_generate",
                "version": 1,
                "veil_lifted": False,
                "is_active": True,
                "template": f"{_EXPLAIN_BASE_TEMPLATE}\n\nKind-specific guidance:\n- {suffix}",
                "vars_json": {
                    "style_profile": style_profile,
                    "max_title_chars": 120,
                    "max_explanation_chars": 720,
                    "max_bullets": 5,
                },
            }
        )
    return rows


def upgrade() -> None:
    op.add_column(
        "ai_prompts",
        sa.Column("veil_lifted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    bind = op.get_bind()
    prompt_table = sa.table(
        "ai_prompts",
        sa.column("name", sa.String(length=64)),
        sa.column("task", sa.String(length=64)),
        sa.column("version", sa.Integer()),
        sa.column("veil_lifted", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("template", sa.Text()),
        sa.column("vars_json", sa.JSON()),
    )
    existing_names = {str(name) for name in bind.execute(sa.select(prompt_table.c.name).distinct()).scalars().all()}
    rows = [row for row in _seed_prompt_rows() if str(row["name"]) not in existing_names]
    if rows:
        op.bulk_insert(prompt_table, rows)


def downgrade() -> None:
    op.drop_column("ai_prompts", "veil_lifted")
