from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ItemT = TypeVar("ItemT")


class HttpContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PageRequest(HttpContract):
    limit: int = Field(default=50, ge=1, le=500)
    page: int = Field(default=1, ge=1)
    sort_by: str | None = None
    sort_order: Literal["asc", "desc"] = "asc"


class CursorPageRequest(HttpContract):
    limit: int = Field(default=50, ge=1, le=500)
    cursor: str | None = None
    sort_by: str | None = None
    sort_order: Literal["asc", "desc"] = "asc"


class SortContract(HttpContract):
    sort_by: str | None = None
    sort_order: Literal["asc", "desc"] | None = None


class PageEnvelope(HttpContract, Generic[ItemT]):
    items: list[ItemT]
    limit: int
    page: int | None = None
    cursor: str | None = None
    next_cursor: str | None = None
    total: int | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: SortContract | None = None
    generated_at: datetime | None = None
    consistency: str | None = None
    staleness_ms: int | None = None


class AcceptedResponse(HttpContract):
    status: Literal["accepted"] = "accepted"
    operation_id: str | None = None
    operation_type: str
    accepted_at: datetime
    deduplicated: bool = False
    message: str | None = None
    correlation_id: str | None = None


class CreatedResponse(HttpContract, Generic[ItemT]):
    status: Literal["created"] = "created"
    item: ItemT


class NoContentResponse(HttpContract):
    status: Literal["no_content"] = "no_content"
