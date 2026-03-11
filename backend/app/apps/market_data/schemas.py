from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.apps.market_data.domain import normalize_interval


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CandleConfig(BaseModel):
    interval: str
    retention_bars: int = Field(gt=0)

    @field_validator("interval")
    @classmethod
    def normalize_interval_value(cls, value: str) -> str:
        return normalize_interval(value)


class CoinBase(BaseModel):
    symbol: str
    name: str
    asset_type: str = "crypto"
    theme: str = "core"
    sector: str | None = None
    source: str = "default"
    enabled: bool = True
    sort_order: int = 0
    candles: list[CandleConfig] = Field(
        default_factory=lambda: [
            CandleConfig(interval="15m", retention_bars=20160),
            CandleConfig(interval="1h", retention_bars=8760),
            CandleConfig(interval="4h", retention_bars=4380),
            CandleConfig(interval="1d", retention_bars=3650),
        ],
    )

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class CoinCreate(CoinBase):
    pass


class CoinRead(CoinBase):
    id: int
    auto_watch_enabled: bool = False
    auto_watch_source: str | None = None
    sector: str = Field(
        validation_alias="sector_code",
        serialization_alias="sector",
    )
    created_at: datetime
    history_backfill_completed_at: datetime | None = None
    last_history_sync_at: datetime | None = None
    next_history_sync_at: datetime | None = None
    last_history_sync_error: str | None = None
    candles: list[CandleConfig] = Field(
        validation_alias="candles_config",
        serialization_alias="candles",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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


__all__ = ["CandleConfig", "CoinCreate", "CoinRead", "PriceHistoryCreate", "PriceHistoryRead"]
