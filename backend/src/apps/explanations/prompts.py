from __future__ import annotations

from dataclasses import dataclass

from src.apps.explanations.contracts import ExplainKind

PROMPT_TASK_EXPLAIN_GENERATE = "explain_generate"
DEFAULT_EXPLAIN_PROMPT_VERSION = 1

EXPLAIN_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["title", "explanation", "bullets"],
    "properties": {
        "title": {"type": "string"},
        "explanation": {"type": "string"},
        "bullets": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 5,
        },
    },
    "additionalProperties": False,
}

_BASE_TEMPLATE = """
You produce a bounded investor-facing explanation from deterministic IRIS context.

Rules:
- Return valid JSON only.
- Do not invent missing facts, prices, catalysts or guarantees.
- Keep the explanation grounded in canonical machine fields.
- Use the effective language exactly as required by the execution contract.
- Explain what the signal or decision means, not what the user must do.
- Keep bullets short and factual.
""".strip()

_KIND_SUFFIXES: dict[ExplainKind, str] = {
    ExplainKind.SIGNAL: "Explain the meaning of the specific signal and its confidence context without pretending it is an executed action.",
    ExplainKind.DECISION: "Explain the specific investment decision using its canonical reason and scoring context without turning it into personalized advice.",
}

_STYLE_PROFILES: dict[ExplainKind, str] = {
    ExplainKind.SIGNAL: "signal_explanation",
    ExplainKind.DECISION: "decision_explanation",
}


@dataclass(frozen=True, slots=True)
class ExplanationPrompt:
    name: str
    task: str
    version: int
    template: str
    vars_json: dict[str, object]


def load_explanation_prompt(explain_kind: ExplainKind) -> ExplanationPrompt:
    return ExplanationPrompt(
        name=f"explain.{explain_kind.value}",
        task=PROMPT_TASK_EXPLAIN_GENERATE,
        version=DEFAULT_EXPLAIN_PROMPT_VERSION,
        template=f"{_BASE_TEMPLATE}\n\nKind-specific guidance:\n- {_KIND_SUFFIXES[explain_kind]}",
        vars_json={
            "style_profile": _STYLE_PROFILES[explain_kind],
            "max_title_chars": 120,
            "max_explanation_chars": 720,
            "max_bullets": 5,
        },
    )


__all__ = [
    "DEFAULT_EXPLAIN_PROMPT_VERSION",
    "EXPLAIN_OUTPUT_SCHEMA",
    "ExplanationPrompt",
    "PROMPT_TASK_EXPLAIN_GENERATE",
    "load_explanation_prompt",
]
