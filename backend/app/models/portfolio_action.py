from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin
    from app.models.market_decision import MarketDecision


class PortfolioAction(Base):
    __tablename__ = "portfolio_actions"
    __table_args__ = (
        Index("ix_portfolio_actions_created_desc", desc("created_at")),
        Index("ix_portfolio_actions_coin_created_desc", "coin_id", desc("created_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    size: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    decision_id: Mapped[int] = mapped_column(ForeignKey("market_decisions.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped["Coin"] = relationship("Coin", back_populates="portfolio_actions")
    decision: Mapped["MarketDecision"] = relationship("MarketDecision")
