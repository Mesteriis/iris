from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db.session import Base

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


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


class PredictionResult(Base):
    __tablename__ = "prediction_results"
    __table_args__ = (
        Index("ux_prediction_results_prediction_id", "prediction_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("market_predictions.id", ondelete="CASCADE"), nullable=False)
    actual_move: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    profit: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    prediction: Mapped["MarketPrediction"] = relationship("MarketPrediction", back_populates="result")


__all__ = ["MarketPrediction", "PredictionResult"]
