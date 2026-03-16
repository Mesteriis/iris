from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iris.core.db.session import Base

if TYPE_CHECKING:
    from iris.apps.market_data.models import Coin


class DiscoveredPattern(Base):
    __tablename__ = "discovered_patterns"

    structure_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_return: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_drawdown: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)


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

    coin: Mapped[Coin] = relationship("Coin", back_populates="market_cycles")


class PatternFeature(Base):
    __tablename__ = "pattern_features"

    feature_slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PatternRegistry(Base):
    __tablename__ = "pattern_registry"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cpu_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    statistics: Mapped[list[PatternStatistic]] = relationship(
        "PatternStatistic",
        back_populates="pattern",
        cascade="all, delete-orphan",
    )


class PatternStatistic(Base):
    __tablename__ = "pattern_statistics"
    __table_args__ = (
        Index("ix_pattern_statistics_temperature_desc", "timeframe", "market_regime", "temperature"),
    )

    pattern_slug: Mapped[str] = mapped_column(ForeignKey("pattern_registry.slug", ondelete="CASCADE"), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    market_regime: Mapped[str] = mapped_column(String(32), primary_key=True, default="all")
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_return: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_drawdown: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    temperature: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pattern: Mapped[PatternRegistry] = relationship("PatternRegistry", back_populates="statistics")


__all__ = [
    "DiscoveredPattern",
    "MarketCycle",
    "PatternFeature",
    "PatternRegistry",
    "PatternStatistic",
]
