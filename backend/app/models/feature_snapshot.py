from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"
    __table_args__ = (
        Index("ix_feature_snapshots_coin_tf_ts_desc", "coin_id", "timeframe", desc("timestamp")),
    )

    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    price_current: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    rsi_14: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    macd: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    trend_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volatility: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    sector_strength: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cycle_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pattern_density: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_score: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)

    coin: Mapped["Coin"] = relationship("Coin", back_populates="feature_snapshots")
