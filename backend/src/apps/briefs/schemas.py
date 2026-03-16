from datetime import datetime
from typing import Any

from pydantic import ConfigDict

from src.apps.briefs.contracts import BriefKind
from src.core.http.contracts import AnalyticalReadContract


class BriefRead(AnalyticalReadContract):
    id: int
    brief_kind: BriefKind
    scope_key: str
    symbol: str | None = None
    coin_id: int | None = None
    content_kind: str
    rendered_locale: str | None = None
    title: str
    summary: str
    bullets: list[str]
    content_json: Any
    refs_json: Any
    context_json: Any
    provider: str
    model: str
    prompt_name: str
    prompt_version: int
    source_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


__all__ = ["BriefRead"]
