from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from src.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval, AIPrompt
from src.core.db.persistence import freeze_json_value


@runtime_checkable
class _SupportsInt(Protocol):
    def __int__(self) -> int: ...


@runtime_checkable
class _SupportsFloat(Protocol):
    def __float__(self) -> float: ...


def _required_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool | int | str | bytes | bytearray):
        return int(value)
    if isinstance(value, _SupportsInt):
        return int(value)
    raise TypeError(f"{field_name} must be int-compatible, got {type(value).__name__}")


def _required_float(value: object, *, field_name: str) -> float:
    if isinstance(value, bool | int | float | str | bytes | bytearray):
        return float(value)
    if isinstance(value, _SupportsFloat):
        return float(value)
    if isinstance(value, _SupportsInt):
        return float(int(value))
    raise TypeError(f"{field_name} must be float-compatible, got {type(value).__name__}")


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


def prompt_read_model_from_orm(prompt: AIPrompt) -> PromptReadModel:
    return PromptReadModel(
        id=_required_int(prompt.id, field_name="id"),
        name=str(prompt.name),
        task=str(prompt.task),
        version=_required_int(prompt.version, field_name="version"),
        veil_lifted=bool(prompt.veil_lifted),
        is_active=bool(prompt.is_active),
        template=str(prompt.template),
        vars_json=freeze_json_value(dict(prompt.vars_json or {})),
        updated_at=prompt.updated_at,
    )


def hypothesis_read_model_from_orm(hypothesis: AIHypothesis) -> HypothesisReadModel:
    return HypothesisReadModel(
        id=_required_int(hypothesis.id, field_name="id"),
        coin_id=_required_int(hypothesis.coin_id, field_name="coin_id"),
        timeframe=_required_int(hypothesis.timeframe, field_name="timeframe"),
        status=str(hypothesis.status),
        hypothesis_type=str(hypothesis.hypothesis_type),
        statement_json=freeze_json_value(dict(hypothesis.statement_json or {})),
        confidence=_required_float(hypothesis.confidence, field_name="confidence"),
        horizon_min=_required_int(hypothesis.horizon_min, field_name="horizon_min"),
        eval_due_at=hypothesis.eval_due_at,
        context_json=freeze_json_value(dict(hypothesis.context_json or {})),
        provider=str(hypothesis.provider),
        model=str(hypothesis.model),
        prompt_name=str(hypothesis.prompt_name),
        prompt_version=_required_int(hypothesis.prompt_version, field_name="prompt_version"),
        source_event_type=str(hypothesis.source_event_type),
        source_stream_id=str(hypothesis.source_stream_id) if hypothesis.source_stream_id is not None else None,
        created_at=hypothesis.created_at,
        updated_at=hypothesis.updated_at,
    )


def hypothesis_eval_read_model_from_orm(evaluation: AIHypothesisEval) -> HypothesisEvalReadModel:
    return HypothesisEvalReadModel(
        id=_required_int(evaluation.id, field_name="id"),
        hypothesis_id=_required_int(evaluation.hypothesis_id, field_name="hypothesis_id"),
        success=bool(evaluation.success),
        score=_required_float(evaluation.score, field_name="score"),
        details_json=freeze_json_value(dict(evaluation.details_json or {})),
        evaluated_at=evaluation.evaluated_at,
    )
