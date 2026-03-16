from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iris.core.db.session import Base

if TYPE_CHECKING:
    from iris.apps.cross_market.models import CoinRelation, Sector
    from iris.apps.indicators.models import CoinMetrics, FeatureSnapshot, IndicatorCache
    from iris.apps.patterns.models import MarketCycle
    from iris.apps.portfolio.models import PortfolioAction, PortfolioBalance, PortfolioPosition
    from iris.apps.predictions.models import MarketPrediction, PredictionResult
    from iris.apps.signals.models import (
        FinalSignal,
        InvestmentDecision,
        MarketDecision,
        RiskMetric,
        Signal,
        SignalHistory,
    )


class Coin(Base):
    __tablename__ = "coins"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="crypto")
    theme: Mapped[str] = mapped_column(String(64), nullable=False, default="core")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_watch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_watch_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sector_code: Mapped[str] = mapped_column("sector", String(32), nullable=False, default="infrastructure")
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

    candles: Mapped[list[Candle]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="Candle.timestamp",
    )
    sector: Mapped[Sector | None] = relationship("Sector", back_populates="coins")
    metrics: Mapped[CoinMetrics | None] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        uselist=False,
    )
    indicator_cache: Mapped[list[IndicatorCache]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="IndicatorCache.timestamp",
    )
    feature_snapshots: Mapped[list[FeatureSnapshot]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="FeatureSnapshot.timestamp",
    )
    signals: Mapped[list[Signal]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="Signal.candle_timestamp",
    )
    signal_history: Mapped[list[SignalHistory]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="SignalHistory.candle_timestamp",
    )
    market_cycles: Mapped[list[MarketCycle]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="MarketCycle.timeframe",
    )
    investment_decisions: Mapped[list[InvestmentDecision]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="InvestmentDecision.created_at",
    )
    market_decisions: Mapped[list[MarketDecision]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="MarketDecision.created_at",
    )
    leading_relations: Mapped[list[CoinRelation]] = relationship(
        "CoinRelation",
        foreign_keys="CoinRelation.leader_coin_id",
        back_populates="leader_coin",
        cascade="all, delete-orphan",
        order_by="CoinRelation.updated_at",
    )
    following_relations: Mapped[list[CoinRelation]] = relationship(
        "CoinRelation",
        foreign_keys="CoinRelation.follower_coin_id",
        back_populates="follower_coin",
        cascade="all, delete-orphan",
        order_by="CoinRelation.updated_at",
    )
    leader_predictions: Mapped[list[MarketPrediction]] = relationship(
        "MarketPrediction",
        foreign_keys="MarketPrediction.leader_coin_id",
        back_populates="leader_coin",
        cascade="all, delete-orphan",
        order_by="MarketPrediction.created_at",
    )
    target_predictions: Mapped[list[MarketPrediction]] = relationship(
        "MarketPrediction",
        foreign_keys="MarketPrediction.target_coin_id",
        back_populates="target_coin",
        cascade="all, delete-orphan",
        order_by="MarketPrediction.created_at",
    )
    portfolio_balances: Mapped[list[PortfolioBalance]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="PortfolioBalance.updated_at",
    )
    portfolio_positions: Mapped[list[PortfolioPosition]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="PortfolioPosition.opened_at",
    )
    portfolio_actions: Mapped[list[PortfolioAction]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="PortfolioAction.created_at",
    )
    risk_metrics: Mapped[list[RiskMetric]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="RiskMetric.timeframe",
    )
    final_signals: Mapped[list[FinalSignal]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="FinalSignal.created_at",
    )


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        Index("ix_candles_coin_id_timestamp", "coin_id", "timestamp"),
        Index("ix_candles_coin_tf_ts_desc", "coin_id", "timeframe", desc("timestamp")),
    )

    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=15)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(Float(53), nullable=False)
    high: Mapped[float] = mapped_column(Float(53), nullable=False)
    low: Mapped[float] = mapped_column(Float(53), nullable=False)
    close: Mapped[float] = mapped_column(Float(53), nullable=False)
    volume: Mapped[float | None] = mapped_column(Float(53), nullable=True)

    coin: Mapped[Coin] = relationship("Coin", back_populates="candles")


__all__ = ["Candle", "Coin"]
