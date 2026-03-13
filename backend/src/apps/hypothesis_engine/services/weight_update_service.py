from __future__ import annotations

from src.apps.hypothesis_engine.constants import (
    AI_EVENT_WEIGHTS_UPDATED,
    WEIGHT_DECAY,
    WEIGHT_POSTERIOR_BASELINE,
    WEIGHT_SCOPE_HYPOTHESIS_TYPE,
)
from src.apps.hypothesis_engine.models import AIWeight
from src.apps.hypothesis_engine.repositories import HypothesisRepository
from src.apps.market_data.domain import utc_now
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.publisher import publish_event


def posterior_mean(alpha: float, beta: float) -> float:
    denominator = max(alpha + beta, 1e-9)
    return float(alpha / denominator)


class WeightUpdateService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._repo = HypothesisRepository(uow.session)

    async def apply(self, eval_id: int) -> None:
        evaluation = await self._repo.get_eval_for_update(eval_id)
        if evaluation is None or evaluation.hypothesis is None:
            return
        event = await self.apply_to_evaluation(evaluation)
        if event is not None:
            event_type, payload = event
            self._uow.add_after_commit_action(
                lambda event_type=event_type, payload=dict(payload): publish_event(event_type, payload)
            )

    async def apply_to_evaluation(self, evaluation) -> tuple[str, dict[str, object]] | None:
        if evaluation.hypothesis is None:
            return None
        hypothesis = evaluation.hypothesis
        weight = await self._repo.get_weight_for_update(scope=WEIGHT_SCOPE_HYPOTHESIS_TYPE, key=hypothesis.hypothesis_type)
        if weight is None:
            weight = await self._repo.add_weight(
                AIWeight(
                    scope=WEIGHT_SCOPE_HYPOTHESIS_TYPE,
                    weight_key=hypothesis.hypothesis_type,
                    alpha=WEIGHT_POSTERIOR_BASELINE,
                    beta=WEIGHT_POSTERIOR_BASELINE,
                )
            )
        weight.alpha = float(weight.alpha) * WEIGHT_DECAY + (1.0 if evaluation.success else 0.0)
        weight.beta = float(weight.beta) * WEIGHT_DECAY + (0.0 if evaluation.success else 1.0)
        weight.updated_at = utc_now()
        await self._uow.flush()
        return (
            AI_EVENT_WEIGHTS_UPDATED,
            {
                "coin_id": int(hypothesis.coin_id),
                "timeframe": int(hypothesis.timeframe),
                "timestamp": utc_now(),
                "hypothesis_id": int(hypothesis.id),
                "scope": WEIGHT_SCOPE_HYPOTHESIS_TYPE,
                "key": hypothesis.hypothesis_type,
                "alpha": float(weight.alpha),
                "beta": float(weight.beta),
                "posterior_mean": posterior_mean(float(weight.alpha), float(weight.beta)),
            },
        )
