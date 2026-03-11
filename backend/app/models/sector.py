from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin
    from app.models.sector_metric import SectorMetric


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
