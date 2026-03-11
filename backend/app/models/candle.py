from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, SmallInteger, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        Index("ix_candles_coin_id_timestamp", "coin_id", "timestamp"),
        Index("ix_candles_coin_tf_ts_desc", "coin_id", "timeframe", desc("timestamp")),
    )

    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=15)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(Float(53), nullable=False)
    high: Mapped[float] = mapped_column(Float(53), nullable=False)
    low: Mapped[float] = mapped_column(Float(53), nullable=False)
    close: Mapped[float] = mapped_column(Float(53), nullable=False)
    volume: Mapped[float | None] = mapped_column(Float(53), nullable=True)

    coin: Mapped["Coin"] = relationship("Coin", back_populates="candles")
