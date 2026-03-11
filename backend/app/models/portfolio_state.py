from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


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
