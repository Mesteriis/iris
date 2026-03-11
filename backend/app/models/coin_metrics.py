from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin


class CoinMetrics(Base):
    __tablename__ = "coin_metrics"
    __table_args__ = (
        Index("ux_coin_metrics_coin_id", "coin_id", unique=True),
        Index("ix_coin_metrics_trend_score_desc", desc("trend_score")),
        Index("ix_coin_metrics_volume_change_24h_desc", desc("volume_change_24h")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    price_current: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    price_change_1h: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    price_change_24h: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    price_change_7d: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    ema_20: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    ema_50: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    sma_50: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    sma_200: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    rsi_14: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    macd: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    macd_signal: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    macd_histogram: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    atr_14: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    bb_upper: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    bb_middle: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    bb_lower: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    bb_width: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    adx_14: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    volume_24h: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    volume_change_24h: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    volatility: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    trend: Mapped[str | None] = mapped_column(String(16), nullable=True)
    trend_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market_regime_details: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    indicator_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped["Coin"] = relationship("Coin", back_populates="metrics")
