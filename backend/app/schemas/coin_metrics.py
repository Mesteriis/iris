from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CoinMetricsRead(BaseModel):
    coin_id: int
    symbol: str
    name: str
    price_current: float | None = None
    price_change_1h: float | None = None
    price_change_24h: float | None = None
    price_change_7d: float | None = None
    ema_20: float | None = None
    ema_50: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    atr_14: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_width: float | None = None
    adx_14: float | None = None
    volume_24h: float | None = None
    volume_change_24h: float | None = None
    volatility: float | None = None
    market_cap: float | None = None
    trend: str | None = None
    trend_score: int | None = None
    market_regime: str | None = None
    market_regime_details: dict[str, dict[str, float | str]] | None = None
    indicator_version: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
