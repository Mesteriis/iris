from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


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

    statistics: Mapped[list["PatternStatistic"]] = relationship(
        "PatternStatistic",
        back_populates="pattern",
        cascade="all, delete-orphan",
    )
