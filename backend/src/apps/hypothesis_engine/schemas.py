from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AIPromptCreate(BaseModel):
    name: str
    task: str
    version: int = Field(default=1, ge=1)
    template: str
    vars_json: dict[str, Any] = Field(default_factory=dict)


class AIPromptUpdate(BaseModel):
    task: str | None = None
    template: str | None = None
    vars_json: dict[str, Any] | None = None
    is_active: bool | None = None


class AIPromptRead(BaseModel):
    id: int
    name: str
    task: str
    version: int
    veil_lifted: bool
    is_active: bool
    template: str
    vars_json: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIHypothesisRead(BaseModel):
    id: int
    coin_id: int
    timeframe: int
    status: str
    hypothesis_type: str
    statement_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    horizon_min: int
    eval_due_at: datetime
    context_json: dict[str, Any] = Field(default_factory=dict)
    provider: str
    model: str
    prompt_name: str
    prompt_version: int
    source_event_type: str
    source_stream_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIHypothesisEvalRead(BaseModel):
    id: int
    hypothesis_id: int
    success: bool
    score: float
    details_json: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIWeightRead(BaseModel):
    id: int
    scope: str
    weight_key: str
    alpha: float
    beta: float
    updated_at: datetime
    posterior_mean: float


class AISSEEnvelope(BaseModel):
    event: str
    payload: dict[str, Any]
