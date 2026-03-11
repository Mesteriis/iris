from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin


class MarketDecision(Base):
    __tablename__ = "market_decisions"
    __table_args__ = (
        Index("ix_market_decisions_coin_tf_created_desc", "coin_id", "timeframe", desc("created_at")),
        Index("ix_market_decisions_confidence_desc", desc("confidence")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped["Coin"] = relationship("Coin", back_populates="market_decisions")
