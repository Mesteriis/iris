from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.coin import Coin
    from app.models.prediction_result import PredictionResult


class MarketPrediction(Base):
    __tablename__ = "market_predictions"
    __table_args__ = (
        Index("ix_market_predictions_status_evaluation_time", "status", "evaluation_time"),
        Index("ix_market_predictions_leader_target_created_desc", "leader_coin_id", "target_coin_id", desc("created_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prediction_type: Mapped[str] = mapped_column(String(64), nullable=False)
    leader_coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    target_coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    prediction_event: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_move: Mapped[str] = mapped_column(String(16), nullable=False)
    lag_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    leader_coin: Mapped["Coin"] = relationship("Coin", foreign_keys=[leader_coin_id], back_populates="leader_predictions")
    target_coin: Mapped["Coin"] = relationship("Coin", foreign_keys=[target_coin_id], back_populates="target_predictions")
    result: Mapped["PredictionResult | None"] = relationship(
        "PredictionResult",
        back_populates="prediction",
        cascade="all, delete-orphan",
        uselist=False,
    )
