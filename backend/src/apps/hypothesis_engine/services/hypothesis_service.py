from __future__ import annotations

from datetime import timedelta
from typing import Any

from src.apps.hypothesis_engine.agents import ReasoningService
from src.apps.hypothesis_engine.constants import (
    AI_EVENT_HYPOTHESIS_CREATED,
    AI_EVENT_INSIGHT,
    SUPPORTED_HYPOTHESIS_SOURCE_EVENTS,
)
from src.apps.hypothesis_engine.models import AIHypothesis
from src.apps.hypothesis_engine.prompts import PromptLoader
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.hypothesis_engine.repositories import HypothesisRepository
from src.apps.market_data.domain import ensure_utc
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.publisher import publish_event
from src.runtime.streams.types import IrisEvent


class HypothesisService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._repo = HypothesisRepository(uow.session)
        self._queries = HypothesisQueryService(uow.session)
        self._reasoning = ReasoningService(PromptLoader(self._queries))

    async def create_from_event(self, event: IrisEvent) -> int:
        if event.event_type not in SUPPORTED_HYPOTHESIS_SOURCE_EVENTS or event.coin_id <= 0:
            return 0
        coin = await self._queries.get_coin_context(event.coin_id)
        if coin is None:
            return 0
        effective_timeframe = int(event.timeframe) if int(event.timeframe) > 0 else 15
        context: dict[str, Any] = {
            "event_type": event.event_type,
            "coin_id": int(event.coin_id),
            "timeframe": effective_timeframe,
            "timestamp": ensure_utc(event.timestamp).isoformat(),
            "payload": dict(event.payload),
            "symbol": coin.symbol,
            "sector": coin.sector_code,
        }
        reasoning = await self._reasoning.generate(context)
        hypothesis = await self._repo.add_hypothesis(
            AIHypothesis(
                coin_id=int(event.coin_id),
                timeframe=effective_timeframe,
                status="active",
                hypothesis_type=reasoning["type"],
                statement_json={
                    "direction": reasoning["direction"],
                    "target_move": reasoning["target_move"],
                    "summary": reasoning["summary"],
                    "assets": list(reasoning["assets"]),
                    "explain": reasoning["explain"],
                    "kind": reasoning["kind"],
                },
                confidence=float(reasoning["confidence"]),
                horizon_min=int(reasoning["horizon_min"]),
                eval_due_at=ensure_utc(event.timestamp) + timedelta(minutes=int(reasoning["horizon_min"])),
                context_json={
                    "symbol": coin.symbol,
                    "sector": coin.sector_code,
                    "trigger_timestamp": ensure_utc(event.timestamp).isoformat(),
                    "source_event_type": event.event_type,
                    "source_payload": dict(event.payload),
                },
                provider=reasoning["provider"],
                model=reasoning["model"],
                prompt_name=reasoning["prompt_name"],
                prompt_version=int(reasoning["prompt_version"]),
                source_event_type=event.event_type,
                source_stream_id=event.stream_id,
            )
        )
        self._uow.add_after_commit_action(
            lambda payload={
                "coin_id": int(hypothesis.coin_id),
                "timeframe": int(hypothesis.timeframe),
                "timestamp": ensure_utc(event.timestamp),
                "hypothesis_id": int(hypothesis.id),
                "type": hypothesis.hypothesis_type,
                "horizon_min": int(hypothesis.horizon_min),
                "confidence": float(hypothesis.confidence),
                "assets": list(hypothesis.statement_json.get("assets", [])),
                "prompt": hypothesis.prompt_name,
                "provider": hypothesis.provider,
            }: publish_event(AI_EVENT_HYPOTHESIS_CREATED, payload)
        )
        self._uow.add_after_commit_action(
            lambda payload={
                "coin_id": int(hypothesis.coin_id),
                "timeframe": int(hypothesis.timeframe),
                "timestamp": ensure_utc(event.timestamp),
                "kind": str(hypothesis.statement_json.get("kind") or "explain"),
                "text": str(hypothesis.statement_json.get("explain") or hypothesis.statement_json.get("summary") or ""),
                "confidence": float(hypothesis.confidence),
                "hypothesis_id": int(hypothesis.id),
            }: publish_event(AI_EVENT_INSIGHT, payload)
        )
        return int(hypothesis.id)
