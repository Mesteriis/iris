from __future__ import annotations

from typing import Any

from src.apps.hypothesis_engine.constants import DEFAULT_HYPOTHESIS_HORIZON_MIN, DEFAULT_TARGET_MOVE
from src.apps.hypothesis_engine.providers.base import LLMProvider


def _signal_direction(signal_type: object) -> str:
    signal = str(signal_type or "").lower()
    if any(token in signal for token in ("bear", "sell", "short", "down")):
        return "down"
    if any(token in signal for token in ("bull", "buy", "long", "up")):
        return "up"
    return "up"


def _decision_direction(decision: object) -> str:
    value = str(decision or "").upper()
    if value in {"SELL", "SHORT", "REDUCE"}:
        return "down"
    if value in {"BUY", "LONG", "ADD"}:
        return "up"
    return "neutral"


class HeuristicProvider(LLMProvider):
    provider_name = "heuristic"

    async def json_chat(self, prompt: str, vars: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        del prompt, schema
        event_type = str(vars.get("event_type", "unknown"))
        payload = dict(vars.get("payload") or {})
        symbol = str(vars.get("symbol") or payload.get("symbol") or f"coin-{int(vars.get('coin_id', 0))}")
        confidence = float(payload.get("confidence") or payload.get("score") or payload.get("regime_confidence") or 0.58)
        confidence = max(0.35, min(confidence, 0.95))
        direction = "neutral"
        hypothesis_type = "event_follow_through"
        if event_type == "signal_created":
            direction = _signal_direction(payload.get("signal_type"))
            hypothesis_type = "signal_follow_through"
        elif event_type == "decision_generated":
            direction = _decision_direction(payload.get("decision"))
            hypothesis_type = "decision_follow_through"
        elif event_type == "market_regime_changed":
            direction = "down" if str(payload.get("regime", "")).startswith("bear") else "up"
            hypothesis_type = "regime_follow_through"
        elif event_type == "anomaly_detected":
            direction = _decision_direction(payload.get("direction_hint") or payload.get("severity"))
            hypothesis_type = "anomaly_follow_through"
        elif event_type.startswith("portfolio_"):
            direction = "neutral"
            hypothesis_type = "portfolio_risk_shift"

        return {
            "type": hypothesis_type,
            "confidence": confidence,
            "horizon_min": int(vars.get("horizon_min") or payload.get("horizon_min") or DEFAULT_HYPOTHESIS_HORIZON_MIN),
            "direction": direction,
            "target_move": float(vars.get("target_move") or payload.get("target_move") or DEFAULT_TARGET_MOVE),
            "summary": f"{symbol} may show {direction} follow-through after {event_type}.",
            "assets": [symbol],
            "explain": f"Trigger {event_type} suggests a testable {direction} continuation window.",
            "kind": "explain",
        }
