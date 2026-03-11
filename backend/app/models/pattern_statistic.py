from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.pattern_registry import PatternRegistry


class PatternStatistic(Base):
    __tablename__ = "pattern_statistics"
    __table_args__ = (
        Index("ix_pattern_statistics_temperature_desc", "timeframe", "temperature"),
    )

    pattern_slug: Mapped[str] = mapped_column(ForeignKey("pattern_registry.slug", ondelete="CASCADE"), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_return: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_drawdown: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    temperature: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pattern: Mapped["PatternRegistry"] = relationship("PatternRegistry", back_populates="statistics")
