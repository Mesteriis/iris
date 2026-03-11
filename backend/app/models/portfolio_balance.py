from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin
    from app.models.exchange_account import ExchangeAccount


class PortfolioBalance(Base):
    __tablename__ = "portfolio_balances"
    __table_args__ = (
        Index("ux_portfolio_balances_account_symbol", "exchange_account_id", "symbol", unique=True),
        Index("ix_portfolio_balances_value_desc", desc("value_usd")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange_account_id: Mapped[int] = mapped_column(
        ForeignKey("exchange_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    balance: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    value_usd: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    exchange_account: Mapped["ExchangeAccount"] = relationship("ExchangeAccount", back_populates="balances")
    coin: Mapped["Coin"] = relationship("Coin", back_populates="portfolio_balances")
