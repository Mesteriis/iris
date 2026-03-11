from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, SmallInteger, String, UniqueConstraint, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin


class SignalHistory(Base):
    __tablename__ = "signal_history"
    __table_args__ = (
        UniqueConstraint(
            "coin_id",
            "timeframe",
            "signal_type",
            "candle_timestamp",
            name="ux_signal_history_coin_tf_type_ts",
        ),
        Index("ix_signal_history_coin_tf_ts_desc", "coin_id", "timeframe", desc("candle_timestamp")),
        Index("ix_signal_history_signal_type_coin_id", "signal_type", "coin_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candle_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    profit_after_24h: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    profit_after_72h: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    maximum_drawdown: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    result_return: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    result_drawdown: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    coin: Mapped["Coin"] = relationship("Coin", back_populates="signal_history")
