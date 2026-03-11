from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin


class MarketCycle(Base):
    __tablename__ = "market_cycles"

    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    cycle_phase: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped["Coin"] = relationship("Coin", back_populates="market_cycles")
