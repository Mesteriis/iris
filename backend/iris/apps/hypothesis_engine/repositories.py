from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from iris.apps.hypothesis_engine.constants import HYPOTHESIS_STATUS_ACTIVE
from iris.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval, AIPrompt, AIWeight
from iris.apps.hypothesis_engine.selectors import prompt_versions_stmt
from iris.core.db.persistence import AsyncRepository


class HypothesisRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="hypothesis_engine", repository_name="HypothesisRepository")

    async def get_prompt_for_update(self, prompt_id: int) -> AIPrompt | None:
        self._log_debug("repo.get_prompt_for_update", mode="write", prompt_id=prompt_id)
        prompt = await self.session.get(AIPrompt, prompt_id)
        self._log_debug("repo.get_prompt_for_update.result", mode="write", found=prompt is not None)
        return prompt

    async def get_prompt_by_name_version(self, *, name: str, version: int) -> AIPrompt | None:
        self._log_debug("repo.get_prompt_by_name_version", mode="write", name=name, version=version)
        prompt = await self.session.scalar(
            select(AIPrompt).where(AIPrompt.name == name, AIPrompt.version == version).limit(1)
        )
        self._log_debug("repo.get_prompt_by_name_version.result", mode="write", found=prompt is not None)
        return prompt

    async def list_prompts_for_update(self, *, name: str | None = None) -> list[AIPrompt]:
        self._log_debug("repo.list_prompts_for_update", mode="write", name=name)
        prompts = list((await self.session.execute(prompt_versions_stmt(name=name))).scalars().all())
        self._log_debug("repo.list_prompts_for_update.result", mode="write", count=len(prompts))
        return prompts

    async def add_prompt(self, prompt: AIPrompt) -> AIPrompt:
        self._log_info("repo.add_prompt", mode="write", name=prompt.name, version=int(prompt.version))
        self.session.add(prompt)
        await self.session.flush()
        await self.session.refresh(prompt)
        return prompt

    async def add_hypothesis(self, hypothesis: AIHypothesis) -> AIHypothesis:
        self._log_info(
            "repo.add_hypothesis",
            mode="write",
            coin_id=int(hypothesis.coin_id),
            timeframe=int(hypothesis.timeframe),
            hypothesis_type=hypothesis.hypothesis_type,
        )
        self.session.add(hypothesis)
        await self.session.flush()
        await self.session.refresh(hypothesis)
        return hypothesis

    async def list_due_hypotheses_for_update(self, now: datetime, *, limit: int) -> list[AIHypothesis]:
        self._log_debug(
            "repo.list_due_hypotheses_for_update",
            mode="write",
            now=now.isoformat(),
            limit=limit,
        )
        rows = (
            await self.session.execute(
                select(AIHypothesis)
                .options(selectinload(AIHypothesis.evals))
                .where(AIHypothesis.status == HYPOTHESIS_STATUS_ACTIVE, AIHypothesis.eval_due_at <= now)
                .order_by(AIHypothesis.eval_due_at.asc(), AIHypothesis.id.asc())
                .limit(max(limit, 1))
            )
        ).scalars().all()
        items = list(rows)
        self._log_debug("repo.list_due_hypotheses_for_update.result", mode="write", count=len(items))
        return items

    async def add_eval(self, evaluation: AIHypothesisEval) -> AIHypothesisEval:
        self._log_info(
            "repo.add_eval",
            mode="write",
            hypothesis_id=int(evaluation.hypothesis_id),
        )
        self.session.add(evaluation)
        await self.session.flush()
        await self.session.refresh(evaluation)
        return evaluation

    async def get_eval_for_update(self, eval_id: int) -> AIHypothesisEval | None:
        self._log_debug("repo.get_eval_for_update", mode="write", eval_id=eval_id)
        evaluation = await self.session.scalar(
            select(AIHypothesisEval)
            .options(selectinload(AIHypothesisEval.hypothesis))
            .where(AIHypothesisEval.id == eval_id)
            .limit(1)
        )
        self._log_debug("repo.get_eval_for_update.result", mode="write", found=evaluation is not None)
        return evaluation

    async def get_weight_for_update(self, *, scope: str, key: str) -> AIWeight | None:
        self._log_debug("repo.get_weight_for_update", mode="write", scope=scope, key=key, lock=True)
        weight = await self.session.scalar(
            select(AIWeight)
            .where(AIWeight.scope == scope, AIWeight.weight_key == key)
            .with_for_update()
            .limit(1)
        )
        self._log_debug("repo.get_weight_for_update.result", mode="write", found=weight is not None)
        return weight

    async def add_weight(self, weight: AIWeight) -> AIWeight:
        self._log_info("repo.add_weight", mode="write", scope=weight.scope, key=weight.weight_key)
        self.session.add(weight)
        await self.session.flush()
        await self.session.refresh(weight)
        return weight

    async def refresh(self, entity: object) -> None:
        await self.session.refresh(entity)


__all__ = ["HypothesisRepository"]
