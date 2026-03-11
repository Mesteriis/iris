from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.strategy import Strategy


class StrategyRule(Base):
    __tablename__ = "strategy_rules"

    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), primary_key=True)
    pattern_slug: Mapped[str] = mapped_column(String(96), primary_key=True)
    regime: Mapped[str] = mapped_column(String(32), nullable=False, default="*")
    sector: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    cycle: Mapped[str] = mapped_column(String(32), nullable=False, default="*")
    min_confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)

    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="rules")
