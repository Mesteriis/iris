from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.sector import Sector


class SectorMetric(Base):
    __tablename__ = "sector_metrics"

    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id", ondelete="CASCADE"), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    sector_strength: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    relative_strength: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    capital_flow: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    volatility: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    sector: Mapped["Sector"] = relationship("Sector", back_populates="metrics")
