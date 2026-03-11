from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, SmallInteger, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin
    from app.models.exchange_account import ExchangeAccount


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        Index("ix_portfolio_positions_coin_tf_status", "coin_id", "timeframe", "status"),
        Index("ix_portfolio_positions_value_desc", desc("position_value")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    exchange_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("exchange_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    position_type: Mapped[str] = mapped_column(String(16), nullable=False, default="spot")
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    position_size: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    position_value: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    stop_loss: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    coin: Mapped["Coin"] = relationship("Coin", back_populates="portfolio_positions")
    exchange_account: Mapped["ExchangeAccount | None"] = relationship("ExchangeAccount", back_populates="positions")
