from datetime import datetime
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ItemT = TypeVar("ItemT")
type ConsistencyClass = Literal["strong", "snapshot", "eventual", "derived", "cached"]
type FreshnessClass = Literal["real_time", "near_real_time", "delayed", "historical", "unknown"]


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


class AnalyticalReadContract(HttpContract):
    generated_at: datetime
    consistency: ConsistencyClass
    freshness_class: FreshnessClass
    staleness_ms: int | None = None


class PageEnvelope[ItemT](HttpContract):
    items: list[ItemT]
    limit: int
    page: int | None = None
    cursor: str | None = None
    next_cursor: str | None = None
    total: int | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: SortContract | None = None
    generated_at: datetime | None = None
    consistency: ConsistencyClass | None = None
    freshness_class: FreshnessClass | None = None
    staleness_ms: int | None = None


class AcceptedResponse(HttpContract):
    status: Literal["accepted"] = "accepted"
    operation_id: str | None = None
    operation_type: str
    accepted_at: datetime
    deduplicated: bool = False
    message: str | None = None
    message_key: str | None = None
    message_params: dict[str, Any] = Field(default_factory=dict)
    locale: str | None = None
    correlation_id: str | None = None


class CreatedResponse[ItemT](HttpContract):
    status: Literal["created"] = "created"
    item: ItemT


class NoContentResponse(HttpContract):
    status: Literal["no_content"] = "no_content"
