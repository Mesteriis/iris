from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.market_data import normalize_interval


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
