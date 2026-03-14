from __future__ import annotations

from dataclasses import dataclass

from src.apps.briefs.contracts import BriefKind

PROMPT_TASK_BRIEF_GENERATE = "brief_generate"
DEFAULT_BRIEF_PROMPT_VERSION = 1

BRIEF_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["title", "summary", "bullets"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
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

_KIND_SUFFIXES: dict[BriefKind, str] = {
    BriefKind.MARKET: "Summarize the current cross-symbol market snapshot without pretending it is a trading instruction.",
    BriefKind.SYMBOL: "Summarize the symbol snapshot across available timeframes and keep the wording investor-facing, not trader-hype.",
    BriefKind.PORTFOLIO: "Summarize allocation, risk concentration and open-position posture without presenting the text as an execution confirmation.",
}

_STYLE_PROFILES: dict[BriefKind, str] = {
    BriefKind.MARKET: "market_snapshot_brief",
    BriefKind.SYMBOL: "symbol_snapshot_brief",
    BriefKind.PORTFOLIO: "portfolio_snapshot_brief",
}


@dataclass(frozen=True, slots=True)
class BriefPrompt:
    name: str
    task: str
    version: int
    template: str
    vars_json: dict[str, object]


def load_brief_prompt(brief_kind: BriefKind) -> BriefPrompt:
    return BriefPrompt(
        name=f"brief.{brief_kind.value}",
        task=PROMPT_TASK_BRIEF_GENERATE,
        version=DEFAULT_BRIEF_PROMPT_VERSION,
        template=f"{_BASE_TEMPLATE}\n\nKind-specific guidance:\n- {_KIND_SUFFIXES[brief_kind]}",
        vars_json={
            "style_profile": _STYLE_PROFILES[brief_kind],
            "max_title_chars": 120,
            "max_summary_chars": 640,
            "max_bullets": 5,
        },
    )


__all__ = [
    "BRIEF_OUTPUT_SCHEMA",
    "BriefPrompt",
    "DEFAULT_BRIEF_PROMPT_VERSION",
    "PROMPT_TASK_BRIEF_GENERATE",
    "load_brief_prompt",
]
