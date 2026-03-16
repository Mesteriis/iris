from pydantic import BaseModel, ConfigDict


class TraceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
