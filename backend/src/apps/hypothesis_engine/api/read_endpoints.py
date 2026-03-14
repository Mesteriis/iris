from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.hypothesis_engine.api.contracts import AIHypothesisEvalRead, AIHypothesisRead
from src.apps.hypothesis_engine.api.deps import HypothesisQueryDep
from src.apps.hypothesis_engine.api.presenters import hypothesis_eval_read, hypothesis_read

router = APIRouter(tags=["hypothesis:read"])


@router.get("/hypotheses", response_model=list[AIHypothesisRead], summary="List hypotheses")
async def read_hypotheses(
    service: HypothesisQueryDep,
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
    coin_id: int | None = Query(default=None, ge=1),
) -> list[AIHypothesisRead]:
    items = await service.list_hypotheses(limit=limit, status=status, coin_id=coin_id)
    return [hypothesis_read(item) for item in items]


@router.get("/evals", response_model=list[AIHypothesisEvalRead], summary="List hypothesis evaluations")
async def read_hypothesis_evals(
    service: HypothesisQueryDep,
    limit: int = Query(default=50, ge=1, le=500),
    hypothesis_id: int | None = Query(default=None, ge=1),
) -> list[AIHypothesisEvalRead]:
    items = await service.list_evals(limit=limit, hypothesis_id=hypothesis_id)
    return [hypothesis_eval_read(item) for item in items]
