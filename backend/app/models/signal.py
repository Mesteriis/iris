from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, SmallInteger, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index(
            "ux_signals_coin_id_timeframe_candle_timestamp_signal_type",
            "coin_id",
            "timeframe",
            "candle_timestamp",
            "signal_type",
            unique=True,
        ),
        Index("ix_signals_coin_id_timeframe_candle_timestamp", "coin_id", "timeframe", "candle_timestamp"),
        Index("ix_signals_pattern_timestamp", "signal_type", "candle_timestamp"),
        Index("ix_signals_coin_timestamp", "coin_id", "candle_timestamp"),
        Index("ix_signals_priority_score_desc", desc("priority_score")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False)
    priority_score: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    context_score: Mapped[float] = mapped_column(Float(53), nullable=False, default=1.0)
    regime_alignment: Mapped[float] = mapped_column(Float(53), nullable=False, default=1.0)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candle_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped["Coin"] = relationship("Coin", back_populates="signals")
