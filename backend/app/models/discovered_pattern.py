from __future__ import annotations

from sqlalchemy import Float, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DiscoveredPattern(Base):
    __tablename__ = "discovered_patterns"

    structure_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_return: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_drawdown: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
