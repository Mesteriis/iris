from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iris.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval, AIPrompt
from iris.apps.hypothesis_engine.read_models import (
    CandleReadModel,
    CoinContextReadModel,
    HypothesisEvalReadModel,
    HypothesisReadModel,
    PromptReadModel,
    hypothesis_eval_read_model_from_orm,
    hypothesis_read_model_from_orm,
    prompt_read_model_from_orm,
)
from iris.apps.hypothesis_engine.selectors import hypotheses_stmt, hypothesis_evals_stmt, prompt_versions_stmt
from iris.apps.market_data.models import Candle, Coin
from iris.core.db.persistence import AsyncQueryService


class HypothesisQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="hypothesis_engine", service_name="HypothesisQueryService")

    async def list_prompts(self, *, name: str | None = None) -> tuple[PromptReadModel, ...]:
        self._log_debug("query.list_prompts", mode="read", name=name)
        rows = (await self.session.execute(prompt_versions_stmt(name=name))).scalars().all()
        items = tuple(prompt_read_model_from_orm(prompt) for prompt in rows)
        self._log_debug("query.list_prompts.result", mode="read", count=len(items))
        return items

    async def get_prompt_read_by_id(self, prompt_id: int) -> PromptReadModel | None:
        self._log_debug("query.get_prompt_read_by_id", mode="read", prompt_id=prompt_id)
        prompt = await self.session.get(AIPrompt, prompt_id)
        if prompt is None:
            self._log_debug("query.get_prompt_read_by_id.result", mode="read", found=False)
            return None
        item = prompt_read_model_from_orm(prompt)
        self._log_debug("query.get_prompt_read_by_id.result", mode="read", found=True)
        return item

    async def get_active_prompt(self, name: str) -> PromptReadModel | None:
        self._log_debug("query.get_active_prompt", mode="read", name=name)
        prompt = await self.session.scalar(
            select(AIPrompt)
            .where(AIPrompt.name == name, AIPrompt.is_active.is_(True))
            .order_by(AIPrompt.version.desc(), AIPrompt.id.desc())
            .limit(1)
        )
        if prompt is None:
            self._log_debug("query.get_active_prompt.result", mode="read", found=False)
            return None
        item = prompt_read_model_from_orm(prompt)
        self._log_debug("query.get_active_prompt.result", mode="read", found=True, version=item.version)
        return item

    async def list_hypotheses(
        self,
        *,
        limit: int,
        status: str | None = None,
        coin_id: int | None = None,
    ) -> tuple[HypothesisReadModel, ...]:
        self._log_debug(
            "query.list_hypotheses",
            mode="read",
            limit=limit,
            status=status,
            coin_id=coin_id,
        )
        rows = (await self.session.execute(hypotheses_stmt(limit=limit, status=status, coin_id=coin_id))).scalars().all()
        items = tuple(hypothesis_read_model_from_orm(hypothesis) for hypothesis in rows)
        self._log_debug("query.list_hypotheses.result", mode="read", count=len(items))
        return items

    async def list_evals(
        self,
        *,
        limit: int,
        hypothesis_id: int | None = None,
    ) -> tuple[HypothesisEvalReadModel, ...]:
        self._log_debug(
            "query.list_evals",
            mode="read",
            limit=limit,
            hypothesis_id=hypothesis_id,
        )
        rows = (await self.session.execute(hypothesis_evals_stmt(limit=limit, hypothesis_id=hypothesis_id))).scalars().all()
        items = tuple(hypothesis_eval_read_model_from_orm(evaluation) for evaluation in rows)
        self._log_debug("query.list_evals.result", mode="read", count=len(items))
        return items

    async def get_coin_context(self, coin_id: int) -> CoinContextReadModel | None:
        self._log_debug("query.get_coin_context", mode="read", coin_id=coin_id)
        row = await self.session.execute(
            select(Coin.id, Coin.symbol, Coin.sector_code).where(Coin.id == coin_id).limit(1)
        )
        result = row.first()
        if result is None:
            self._log_debug("query.get_coin_context.result", mode="read", found=False)
            return None
        item = CoinContextReadModel(
            coin_id=int(result.id),
            symbol=str(result.symbol),
            sector_code=str(result.sector_code) if result.sector_code is not None else None,
        )
        self._log_debug("query.get_coin_context.result", mode="read", found=True)
        return item

    async def get_candle_window(
        self,
        *,
        coin_id: int,
        timeframe: int,
        start: datetime,
        end: datetime,
    ) -> tuple[CandleReadModel, ...]:
        self._log_debug(
            "query.get_candle_window",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        rows = (
            await self.session.execute(
                select(Candle.timestamp, Candle.close)
                .where(
                    Candle.coin_id == coin_id,
                    Candle.timeframe == timeframe,
                    Candle.timestamp >= start,
                    Candle.timestamp <= end,
                )
                .order_by(Candle.timestamp.asc())
            )
        ).all()
        items = tuple(CandleReadModel(timestamp=row.timestamp, close=float(row.close)) for row in rows)
        self._log_debug("query.get_candle_window.result", mode="read", count=len(items))
        return items


__all__ = ["HypothesisQueryService"]
