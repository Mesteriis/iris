from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.hypothesis_engine.constants import AI_EVENT_HYPOTHESIS_EVALUATED, AI_EVENT_INSIGHT, HYPOTHESIS_STATUS_EVALUATED
from src.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval
from src.apps.hypothesis_engine.repos import HypothesisRepo
from src.apps.hypothesis_engine.services.weight_update_service import WeightUpdateService
from src.apps.market_data.domain import ensure_utc
from src.runtime.streams.publisher import publish_event


@dataclass(slots=True, frozen=True)
class HypothesisOutcome:
    success: bool
    score: float
    details: dict[str, object]


def _outcome_score(*, direction: str, realized_return: float, target_move: float) -> tuple[bool, float]:
    threshold = max(target_move, 0.001)
    if direction == "down":
        progress = (-realized_return) / threshold
        return progress >= 1.0, max(0.0, min((progress + 1.0) / 2.0, 1.0))
    if direction == "neutral":
        drift = abs(realized_return) / threshold
        return drift <= 1.0, max(0.0, min(1.0 - (drift / 2.0), 1.0))
    progress = realized_return / threshold
    return progress >= 1.0, max(0.0, min((progress + 1.0) / 2.0, 1.0))


class EvaluationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = HypothesisRepo(db)
        self._weights = WeightUpdateService(db)

    async def evaluate_due(self, now: datetime) -> list[int]:
        due_hypotheses = await self._repo.list_due_hypotheses(ensure_utc(now), limit=200)
        created_eval_ids: list[int] = []
        for hypothesis in due_hypotheses:
            outcome = await self._evaluate_hypothesis(hypothesis, now=ensure_utc(now))
            if outcome is None:
                continue
            evaluation = await self._repo.create_eval(
                AIHypothesisEval(
                    hypothesis_id=int(hypothesis.id),
                    success=outcome.success,
                    score=outcome.score,
                    details_json=dict(outcome.details),
                    evaluated_at=ensure_utc(now),
                )
            )
            hypothesis.status = HYPOTHESIS_STATUS_EVALUATED
            await self._db.commit()
            await self._db.refresh(hypothesis)
            publish_event(
                AI_EVENT_HYPOTHESIS_EVALUATED,
                {
                    "coin_id": int(hypothesis.coin_id),
                    "timeframe": int(hypothesis.timeframe),
                    "timestamp": ensure_utc(now),
                    "hypothesis_id": int(hypothesis.id),
                    "success": bool(evaluation.success),
                    "score": float(evaluation.score),
                    "type": hypothesis.hypothesis_type,
                    "details": dict(evaluation.details_json or {}),
                },
            )
            publish_event(
                AI_EVENT_INSIGHT,
                {
                    "coin_id": int(hypothesis.coin_id),
                    "timeframe": int(hypothesis.timeframe),
                    "timestamp": ensure_utc(now),
                    "kind": "evaluation",
                    "text": (
                        f"Hypothesis {int(hypothesis.id)} evaluated as "
                        f"{'successful' if evaluation.success else 'unsuccessful'}."
                    ),
                    "confidence": float(hypothesis.confidence),
                    "hypothesis_id": int(hypothesis.id),
                },
            )
            await self._weights.apply(int(evaluation.id))
            created_eval_ids.append(int(evaluation.id))
        return created_eval_ids

    async def _evaluate_hypothesis(self, hypothesis: AIHypothesis, *, now: datetime) -> HypothesisOutcome | None:
        trigger_raw = hypothesis.context_json.get("trigger_timestamp")
        if not isinstance(trigger_raw, str):
            return None
        start = ensure_utc(datetime.fromisoformat(trigger_raw))
        end = min(ensure_utc(now), ensure_utc(hypothesis.eval_due_at))
        candles = await self._repo.get_candles_between(
            coin_id=int(hypothesis.coin_id),
            timeframe=int(hypothesis.timeframe),
            start=start,
            end=end,
        )
        if len(candles) < 2:
            return None
        entry_price = float(candles[0].close)
        exit_price = float(candles[-1].close)
        realized_return = (exit_price - entry_price) / entry_price if entry_price else 0.0
        direction = str(hypothesis.statement_json.get("direction") or "neutral")
        target_move = float(hypothesis.statement_json.get("target_move") or 0.015)
        success, score = _outcome_score(direction=direction, realized_return=realized_return, target_move=target_move)
        return HypothesisOutcome(
            success=success,
            score=score,
            details={
                "direction": direction,
                "target_move": target_move,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "realized_return": realized_return,
                "bars_used": len(candles),
                "window_start": candles[0].timestamp.isoformat(),
                "window_end": candles[-1].timestamp.isoformat(),
            },
        )
