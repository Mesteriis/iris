from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.strategy import Strategy


class StrategyPerformance(Base):
    __tablename__ = "strategy_performance"

    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), primary_key=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_return: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="performance")
