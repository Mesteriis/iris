from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.candle import Candle
    from app.models.coin_metrics import CoinMetrics
    from app.models.feature_snapshot import FeatureSnapshot
    from app.models.final_signal import FinalSignal
    from app.models.indicator_cache import IndicatorCache
    from app.models.investment_decision import InvestmentDecision
    from app.models.market_cycle import MarketCycle
    from app.models.market_decision import MarketDecision
    from app.models.risk_metric import RiskMetric
    from app.models.sector import Sector
    from app.models.signal import Signal
    from app.models.signal_history import SignalHistory


class Coin(Base):
    __tablename__ = "coins"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="crypto")
    theme: Mapped[str] = mapped_column(String(64), nullable=False, default="core")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id", ondelete="SET NULL"), nullable=True)
    candles_config: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    history_backfill_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_history_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_history_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_history_sync_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    candles: Mapped[list["Candle"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="Candle.timestamp",
    )
    sector: Mapped["Sector | None"] = relationship("Sector", back_populates="coins")
    metrics: Mapped["CoinMetrics | None"] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        uselist=False,
    )
    indicator_cache: Mapped[list["IndicatorCache"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="IndicatorCache.timestamp",
    )
    feature_snapshots: Mapped[list["FeatureSnapshot"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="FeatureSnapshot.timestamp",
    )
    signals: Mapped[list["Signal"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="Signal.candle_timestamp",
    )
    signal_history: Mapped[list["SignalHistory"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="SignalHistory.candle_timestamp",
    )
    market_cycles: Mapped[list["MarketCycle"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="MarketCycle.timeframe",
    )
    investment_decisions: Mapped[list["InvestmentDecision"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="InvestmentDecision.created_at",
    )
    market_decisions: Mapped[list["MarketDecision"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="MarketDecision.created_at",
    )
    risk_metrics: Mapped[list["RiskMetric"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="RiskMetric.timeframe",
    )
    final_signals: Mapped[list["FinalSignal"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="FinalSignal.created_at",
    )
