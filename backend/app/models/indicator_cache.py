from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin


class IndicatorCache(Base):
    __tablename__ = "indicator_cache"
    __table_args__ = (
        Index("ix_indicator_cache_coin_id_timeframe_timestamp_desc", "coin_id", "timeframe", desc("timestamp")),
        Index(
            "ux_ind_cache_coin_tf_ind_ts_ver",
            "coin_id",
            "timeframe",
            "indicator",
            "timestamp",
            "indicator_version",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    indicator: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    indicator_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    feature_source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped["Coin"] = relationship("Coin", back_populates="indicator_cache")
