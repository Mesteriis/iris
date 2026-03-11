from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.strategy_performance import StrategyPerformance
    from app.models.strategy_rule import StrategyRule


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    rules: Mapped[list["StrategyRule"]] = relationship(
        "StrategyRule",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyRule.pattern_slug",
    )
    performance: Mapped["StrategyPerformance | None"] = relationship(
        "StrategyPerformance",
        back_populates="strategy",
        cascade="all, delete-orphan",
        uselist=False,
    )
