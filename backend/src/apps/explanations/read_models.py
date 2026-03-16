from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.apps.explanations.contracts import ExplainKind
from src.core.db.persistence import freeze_json_value


@dataclass(slots=True, frozen=True)
class ExplanationReadModel:
    id: int
    explain_kind: ExplainKind
    subject_id: int
    coin_id: int | None
    symbol: str | None
    timeframe: int | None
    content_kind: str
    content_json: Any
    refs_json: Any
    context_json: Any
    provider: str
    model: str
    prompt_name: str
    prompt_version: int
    subject_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class ExplanationContextBundle:
    explain_kind: ExplainKind
    subject_id: int
    coin_id: int | None
    symbol: str | None
    timeframe: int | None
    subject_updated_at: datetime | None
    context: dict[str, Any]
    refs_json: dict[str, Any]


def explanation_read_model_from_orm(item) -> ExplanationReadModel:
    return ExplanationReadModel(
        id=int(item.id),
        explain_kind=ExplainKind(str(item.explain_kind)),
        subject_id=int(item.subject_id),
        coin_id=int(item.coin_id) if item.coin_id is not None else None,
        symbol=str(item.symbol) if item.symbol is not None else None,
        timeframe=int(item.timeframe) if item.timeframe is not None else None,
        content_kind=str(item.content_kind),
        content_json=freeze_json_value(dict(item.content_json or {})),
        refs_json=freeze_json_value(dict(item.refs_json or {})),
        context_json=freeze_json_value(dict(item.context_json or {})),
        provider=str(item.provider),
        model=str(item.model),
        prompt_name=str(item.prompt_name),
        prompt_version=int(item.prompt_version),
        subject_updated_at=item.subject_updated_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


__all__ = ["ExplanationContextBundle", "ExplanationReadModel", "explanation_read_model_from_orm"]
