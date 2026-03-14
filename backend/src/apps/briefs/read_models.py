from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.apps.briefs.contracts import BriefKind
from src.core.ai import AIContextFormat
from src.core.db.persistence import freeze_json_value


@dataclass(slots=True, frozen=True)
class BriefReadModel:
    id: int
    brief_kind: BriefKind
    scope_key: str
    symbol: str | None
    coin_id: int | None
    language: str
    title: str
    summary: str
    bullets: tuple[str, ...]
    refs_json: Any
    context_json: Any
    provider: str
    model: str
    prompt_name: str
    prompt_version: int
    source_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class BriefContextBundle:
    brief_kind: BriefKind
    scope_key: str
    symbol: str | None
    coin_id: int | None
    source_updated_at: datetime | None
    preferred_context_format: AIContextFormat
    context: dict[str, Any]
    refs_json: dict[str, Any]


def brief_read_model_from_orm(item) -> BriefReadModel:
    return BriefReadModel(
        id=int(item.id),
        brief_kind=BriefKind(str(item.brief_kind)),
        scope_key=str(item.scope_key),
        symbol=str(item.symbol) if item.symbol is not None else None,
        coin_id=int(item.coin_id) if item.coin_id is not None else None,
        language=str(item.language),
        title=str(item.title),
        summary=str(item.summary),
        bullets=tuple(str(row) for row in (item.bullets_json or [])),
        refs_json=freeze_json_value(dict(item.refs_json or {})),
        context_json=freeze_json_value(dict(item.context_json or {})),
        provider=str(item.provider),
        model=str(item.model),
        prompt_name=str(item.prompt_name),
        prompt_version=int(item.prompt_version),
        source_updated_at=item.source_updated_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


__all__ = ["BriefContextBundle", "BriefReadModel", "brief_read_model_from_orm"]
