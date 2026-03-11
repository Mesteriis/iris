from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.session import Base

if TYPE_CHECKING:
    from app.apps.market_data.models import Coin


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coins: Mapped[list["Coin"]] = relationship("Coin", back_populates="sector")
    metrics: Mapped[list["SectorMetric"]] = relationship(
        "SectorMetric",
        back_populates="sector",
        cascade="all, delete-orphan",
        order_by="SectorMetric.timeframe",
    )


class SectorMetric(Base):
    __tablename__ = "sector_metrics"

    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id", ondelete="CASCADE"), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    sector_strength: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    relative_strength: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    capital_flow: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_price_change_24h: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_volume_change_24h: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    volatility: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    trend: Mapped[str | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    sector: Mapped["Sector"] = relationship("Sector", back_populates="metrics")


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
    follower_coin: Mapped["Coin"] = relationship(
        "Coin",
        foreign_keys=[follower_coin_id],
        back_populates="following_relations",
    )


__all__ = ["Sector", "SectorMetric", "CoinRelation"]
