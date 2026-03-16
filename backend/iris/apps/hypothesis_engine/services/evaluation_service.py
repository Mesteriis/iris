from dataclasses import dataclass
from datetime import datetime

from iris.apps.hypothesis_engine.constants import (
    AI_EVENT_HYPOTHESIS_EVALUATED,
    AI_EVENT_INSIGHT,
    HYPOTHESIS_STATUS_EVALUATED,
)
from iris.apps.hypothesis_engine.contracts import (
    HypothesisEvaluationBatchResult,
    HypothesisPendingEvent,
)
from iris.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval
from iris.apps.hypothesis_engine.query_services import HypothesisQueryService
from iris.apps.hypothesis_engine.repositories import HypothesisRepository
from iris.apps.hypothesis_engine.services.weight_update_service import WeightUpdateService
from iris.apps.market_data.domain import ensure_utc
from iris.core.db.uow import BaseAsyncUnitOfWork


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
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._repo = HypothesisRepository(uow.session)
        self._queries = HypothesisQueryService(uow.session)
        self._weights = WeightUpdateService(uow)

    async def evaluate_due(self, now: datetime) -> HypothesisEvaluationBatchResult:
        due_hypotheses = await self._repo.list_due_hypotheses_for_update(ensure_utc(now), limit=200)
        created_eval_ids: list[int] = []
        pending_events: list[HypothesisPendingEvent] = []
        for hypothesis in due_hypotheses:
            outcome = await self._evaluate_hypothesis(hypothesis, now=ensure_utc(now))
            if outcome is None:
                continue
            evaluation = await self._repo.add_eval(
                AIHypothesisEval(
                    hypothesis_id=int(hypothesis.id),
                    success=outcome.success,
                    score=outcome.score,
                    details_json=dict(outcome.details),
                    evaluated_at=ensure_utc(now),
                )
            )
            hypothesis.status = HYPOTHESIS_STATUS_EVALUATED
            pending_events.append(
                HypothesisPendingEvent(
                    event_type=AI_EVENT_HYPOTHESIS_EVALUATED,
                    payload={
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
            )
            pending_events.append(
                HypothesisPendingEvent(
                    event_type=AI_EVENT_INSIGHT,
                    payload={
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
            )
            weight_result = await self._weights.apply_to_evaluation(evaluation)
            pending_events.extend(weight_result.pending_events)
            created_eval_ids.append(int(evaluation.id))
        return HypothesisEvaluationBatchResult(
            evaluation_ids=tuple(created_eval_ids),
            pending_events=tuple(pending_events),
        )

    async def _evaluate_hypothesis(self, hypothesis: AIHypothesis, *, now: datetime) -> HypothesisOutcome | None:
        trigger_raw = hypothesis.context_json.get("trigger_timestamp")
        if not isinstance(trigger_raw, str):
            return None
        start = ensure_utc(datetime.fromisoformat(trigger_raw))
        end = min(ensure_utc(now), ensure_utc(hypothesis.eval_due_at))
        candles = await self._queries.get_candle_window(
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
