from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.hypothesis_engine.constants import AI_EVENT_WEIGHTS_UPDATED, WEIGHT_DECAY, WEIGHT_POSTERIOR_BASELINE, WEIGHT_SCOPE_HYPOTHESIS_TYPE
from src.apps.hypothesis_engine.models import AIWeight
from src.apps.hypothesis_engine.repos import HypothesisRepo
from src.apps.market_data.domain import utc_now
from src.runtime.streams.publisher import publish_event


def posterior_mean(alpha: float, beta: float) -> float:
    denominator = max(alpha + beta, 1e-9)
    return float(alpha / denominator)


class WeightUpdateService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = HypothesisRepo(db)

    async def apply(self, eval_id: int) -> None:
        evaluation = await self._repo.get_eval(eval_id)
        if evaluation is None or evaluation.hypothesis is None:
            return
        hypothesis = evaluation.hypothesis
        weight = await self._repo.get_weight(scope=WEIGHT_SCOPE_HYPOTHESIS_TYPE, key=hypothesis.hypothesis_type)
        if weight is None:
            weight = AIWeight(
                scope=WEIGHT_SCOPE_HYPOTHESIS_TYPE,
                weight_key=hypothesis.hypothesis_type,
                alpha=WEIGHT_POSTERIOR_BASELINE,
                beta=WEIGHT_POSTERIOR_BASELINE,
            )
            self._db.add(weight)
            await self._db.flush()
        weight.alpha = float(weight.alpha) * WEIGHT_DECAY + (1.0 if evaluation.success else 0.0)
        weight.beta = float(weight.beta) * WEIGHT_DECAY + (0.0 if evaluation.success else 1.0)
        weight.updated_at = utc_now()
        await self._db.commit()
        await self._db.refresh(weight)
        publish_event(
            AI_EVENT_WEIGHTS_UPDATED,
            {
                "coin_id": int(hypothesis.coin_id),
                "timeframe": int(hypothesis.timeframe),
                "timestamp": utc_now(),
                "hypothesis_id": int(hypothesis.id),
                "scope": weight.scope,
                "key": weight.weight_key,
                "alpha": float(weight.alpha),
                "beta": float(weight.beta),
                "posterior_mean": posterior_mean(float(weight.alpha), float(weight.beta)),
            },
        )
