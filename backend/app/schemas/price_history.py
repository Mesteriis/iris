from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.market_data import normalize_interval


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PriceHistoryBase(BaseModel):
    interval: str = "1h"
    timestamp: datetime = Field(default_factory=utc_now)
    price: float = Field(gt=0)
    volume: float | None = Field(default=None, ge=0)

    @field_validator("interval")
    @classmethod
    def normalize_interval_value(cls, value: str) -> str:
        return normalize_interval(value)


class PriceHistoryCreate(PriceHistoryBase):
    pass


class PriceHistoryRead(PriceHistoryBase):
    coin_id: int

    model_config = ConfigDict(from_attributes=True)
