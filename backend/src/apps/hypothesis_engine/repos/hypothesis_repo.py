from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval, AIPrompt, AIWeight
from src.apps.hypothesis_engine.selectors import due_hypotheses_stmt, hypothesis_evals_stmt, hypotheses_stmt, prompt_versions_stmt
from src.apps.market_data.models import Candle, Coin


class HypothesisRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_coin(self, coin_id: int) -> Coin | None:
        return await self._db.get(Coin, coin_id)

    async def list_prompts(self, *, name: str | None = None) -> list[AIPrompt]:
        return (await self._db.execute(prompt_versions_stmt(name=name))).scalars().all()

    async def get_prompt(self, prompt_id: int) -> AIPrompt | None:
        return await self._db.get(AIPrompt, prompt_id)

    async def get_prompt_by_name_version(self, *, name: str, version: int) -> AIPrompt | None:
        return await self._db.scalar(
            select(AIPrompt).where(AIPrompt.name == name, AIPrompt.version == version).limit(1)
        )

    async def create_prompt(self, prompt: AIPrompt) -> AIPrompt:
        self._db.add(prompt)
        await self._db.commit()
        await self._db.refresh(prompt)
        return prompt

    async def create_hypothesis(self, hypothesis: AIHypothesis) -> AIHypothesis:
        self._db.add(hypothesis)
        await self._db.commit()
        await self._db.refresh(hypothesis)
        return hypothesis

    async def list_hypotheses(
        self,
        *,
        limit: int,
        status: str | None = None,
        coin_id: int | None = None,
    ) -> list[AIHypothesis]:
        return (await self._db.execute(hypotheses_stmt(limit=limit, status=status, coin_id=coin_id))).scalars().all()

    async def list_due_hypotheses(self, now: datetime, *, limit: int) -> list[AIHypothesis]:
        return (await self._db.execute(due_hypotheses_stmt(now, limit=limit))).scalars().all()

    async def list_evals(self, *, limit: int, hypothesis_id: int | None = None) -> list[AIHypothesisEval]:
        return (await self._db.execute(hypothesis_evals_stmt(limit=limit, hypothesis_id=hypothesis_id))).scalars().all()

    async def create_eval(self, evaluation: AIHypothesisEval) -> AIHypothesisEval:
        self._db.add(evaluation)
        await self._db.commit()
        await self._db.refresh(evaluation)
        return evaluation

    async def get_eval(self, eval_id: int) -> AIHypothesisEval | None:
        return await self._db.scalar(
            select(AIHypothesisEval)
            .options(selectinload(AIHypothesisEval.hypothesis))
            .where(AIHypothesisEval.id == eval_id)
            .limit(1)
        )

    async def get_weight(self, *, scope: str, key: str) -> AIWeight | None:
        return await self._db.scalar(
            select(AIWeight).where(AIWeight.scope == scope, AIWeight.weight_key == key).limit(1)
        )

    async def get_candles_between(
        self,
        *,
        coin_id: int,
        timeframe: int,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        return (
            await self._db.execute(
                select(Candle)
                .where(
                    Candle.coin_id == coin_id,
                    Candle.timeframe == timeframe,
                    Candle.timestamp >= start,
                    Candle.timestamp <= end,
                )
                .order_by(Candle.timestamp.asc())
            )
        ).scalars().all()
