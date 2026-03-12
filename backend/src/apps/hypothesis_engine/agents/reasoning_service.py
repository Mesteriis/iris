from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.hypothesis_engine.constants import (
    DEFAULT_HYPOTHESIS_HORIZON_MIN,
    DEFAULT_PROMPT_NAME,
    DEFAULT_TARGET_MOVE,
    EVENT_PROMPT_NAMES,
    PROVIDER_HEURISTIC,
)
from src.apps.hypothesis_engine.prompts import HYPOTHESIS_OUTPUT_SCHEMA, PromptLoader
from src.apps.hypothesis_engine.providers import create_provider


class ReasoningService:
    def __init__(self, db: AsyncSession | None = None) -> None:
        self._db = db
        self._loader = PromptLoader(db)

    async def generate(self, ctx: dict[str, Any]) -> dict[str, Any]:
        event_type = str(ctx.get("event_type") or "")
        prompt_name = str(ctx.get("prompt_name") or EVENT_PROMPT_NAMES.get(event_type, DEFAULT_PROMPT_NAME))
        prompt = await self._loader.load(prompt_name)
        provider_name = str(prompt.vars_json.get("provider") or PROVIDER_HEURISTIC)
        provider_config = dict(prompt.vars_json)
        merged_ctx = {
            **prompt.vars_json,
            **ctx,
        }
        provider = create_provider(provider_name, model=str(provider_config.get("model") or ""), config=provider_config)
        try:
            response = await provider.json_chat(prompt.template, vars=merged_ctx, schema=HYPOTHESIS_OUTPUT_SCHEMA)
        except Exception:
            fallback = create_provider(PROVIDER_HEURISTIC, model="rule-based", config=prompt.vars_json)
            response = await fallback.json_chat(prompt.template, vars=merged_ctx, schema=HYPOTHESIS_OUTPUT_SCHEMA)
            provider_name = PROVIDER_HEURISTIC
            provider = fallback

        assets = [str(asset) for asset in response.get("assets", []) if str(asset).strip()]
        if not assets and ctx.get("symbol") is not None:
            assets = [str(ctx["symbol"])]
        return {
            "type": str(response.get("type") or "event_follow_through"),
            "confidence": max(0.0, min(float(response.get("confidence") or 0.0), 1.0)),
            "horizon_min": max(int(response.get("horizon_min") or DEFAULT_HYPOTHESIS_HORIZON_MIN), 1),
            "direction": str(response.get("direction") or "neutral"),
            "target_move": max(float(response.get("target_move") or DEFAULT_TARGET_MOVE), 0.001),
            "summary": str(response.get("summary") or "Event-triggered hypothesis generated."),
            "assets": assets,
            "explain": str(response.get("explain") or response.get("summary") or "No explanation provided."),
            "kind": str(response.get("kind") or "explain"),
            "provider": provider_name,
            "model": provider.model,
            "prompt_name": prompt.name,
            "prompt_version": int(prompt.version),
        }
