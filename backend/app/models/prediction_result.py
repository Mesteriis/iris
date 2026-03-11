from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.market_prediction import MarketPrediction


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
