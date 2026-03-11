from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.portfolio_balance import PortfolioBalance
    from app.models.portfolio_position import PortfolioPosition


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

    balances: Mapped[list["PortfolioBalance"]] = relationship(
        "PortfolioBalance",
        back_populates="exchange_account",
        cascade="all, delete-orphan",
        order_by="PortfolioBalance.updated_at",
    )
    positions: Mapped[list["PortfolioPosition"]] = relationship(
        "PortfolioPosition",
        back_populates="exchange_account",
        cascade="all, delete-orphan",
        order_by="PortfolioPosition.opened_at",
    )
