from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, SmallInteger, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iris.core.db.session import Base

if TYPE_CHECKING:
    from iris.apps.market_data.models import Coin
    from iris.apps.signals.models import MarketDecision


class ExchangeAccount(Base):
    __tablename__ = "exchange_accounts"
    __table_args__ = (
        Index("ix_exchange_accounts_exchange_enabled", "exchange_name", "enabled"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_name: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key: Mapped[str] = mapped_column(String(255), nullable=False)
    api_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    balances: Mapped[list[PortfolioBalance]] = relationship(
        "PortfolioBalance",
        back_populates="exchange_account",
        cascade="all, delete-orphan",
        order_by="PortfolioBalance.updated_at",
    )
    positions: Mapped[list[PortfolioPosition]] = relationship(
        "PortfolioPosition",
        back_populates="exchange_account",
        cascade="all, delete-orphan",
        order_by="PortfolioPosition.opened_at",
    )


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

    coin: Mapped[Coin] = relationship("Coin", back_populates="portfolio_actions")
    decision: Mapped[MarketDecision] = relationship("MarketDecision")


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

    exchange_account: Mapped[ExchangeAccount] = relationship("ExchangeAccount", back_populates="balances")
    coin: Mapped[Coin] = relationship("Coin", back_populates="portfolio_balances")


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

    coin: Mapped[Coin] = relationship("Coin", back_populates="portfolio_positions")
    exchange_account: Mapped[ExchangeAccount | None] = relationship("ExchangeAccount", back_populates="positions")


class PortfolioState(Base):
    __tablename__ = "portfolio_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    total_capital: Mapped[float] = mapped_column(Float(53), nullable=False, default=100_000.0)
    allocated_capital: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    available_capital: Mapped[float] = mapped_column(Float(53), nullable=False, default=100_000.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


__all__ = [
    "ExchangeAccount",
    "PortfolioAction",
    "PortfolioBalance",
    "PortfolioPosition",
    "PortfolioState",
]
