from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.core.db.persistence import freeze_json_value


@dataclass(slots=True, frozen=True)
class PromptReadModel:
    id: int
    name: str
    task: str
    version: int
    veil_lifted: bool
    is_active: bool
    template: str
    vars_json: Any
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class HypothesisReadModel:
    id: int
    coin_id: int
    timeframe: int
    status: str
    hypothesis_type: str
    statement_json: Any
    confidence: float
    horizon_min: int
    eval_due_at: datetime
    context_json: Any
    provider: str
    model: str
    prompt_name: str
    prompt_version: int
    source_event_type: str
    source_stream_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class HypothesisEvalReadModel:
    id: int
    hypothesis_id: int
    success: bool
    score: float
    details_json: Any
    evaluated_at: datetime


@dataclass(slots=True, frozen=True)
class CoinContextReadModel:
    coin_id: int
    symbol: str
    sector_code: str | None


@dataclass(slots=True, frozen=True)
class CandleReadModel:
    timestamp: datetime
    close: float


def prompt_read_model_from_orm(prompt) -> PromptReadModel:
    return PromptReadModel(
        id=int(prompt.id),
        name=str(prompt.name),
        task=str(prompt.task),
        version=int(prompt.version),
        veil_lifted=bool(prompt.veil_lifted),
        is_active=bool(prompt.is_active),
        template=str(prompt.template),
        vars_json=freeze_json_value(dict(prompt.vars_json or {})),
        updated_at=prompt.updated_at,
    )


def hypothesis_read_model_from_orm(hypothesis) -> HypothesisReadModel:
    return HypothesisReadModel(
        id=int(hypothesis.id),
        coin_id=int(hypothesis.coin_id),
        timeframe=int(hypothesis.timeframe),
        status=str(hypothesis.status),
        hypothesis_type=str(hypothesis.hypothesis_type),
        statement_json=freeze_json_value(dict(hypothesis.statement_json or {})),
        confidence=float(hypothesis.confidence),
        horizon_min=int(hypothesis.horizon_min),
        eval_due_at=hypothesis.eval_due_at,
        context_json=freeze_json_value(dict(hypothesis.context_json or {})),
        provider=str(hypothesis.provider),
        model=str(hypothesis.model),
        prompt_name=str(hypothesis.prompt_name),
        prompt_version=int(hypothesis.prompt_version),
        source_event_type=str(hypothesis.source_event_type),
        source_stream_id=str(hypothesis.source_stream_id) if hypothesis.source_stream_id is not None else None,
        created_at=hypothesis.created_at,
        updated_at=hypothesis.updated_at,
    )


def hypothesis_eval_read_model_from_orm(evaluation) -> HypothesisEvalReadModel:
    return HypothesisEvalReadModel(
        id=int(evaluation.id),
        hypothesis_id=int(evaluation.hypothesis_id),
        success=bool(evaluation.success),
        score=float(evaluation.score),
        details_json=freeze_json_value(dict(evaluation.details_json or {})),
        evaluated_at=evaluation.evaluated_at,
    )
