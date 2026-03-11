from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin


class CoinRelation(Base):
    __tablename__ = "coin_relations"
    __table_args__ = (
        Index("ux_coin_relations_leader_follower", "leader_coin_id", "follower_coin_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    leader_coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    follower_coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    correlation: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    lag_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    leader_coin: Mapped["Coin"] = relationship("Coin", foreign_keys=[leader_coin_id], back_populates="leading_relations")
    follower_coin: Mapped["Coin"] = relationship("Coin", foreign_keys=[follower_coin_id], back_populates="following_relations")
