from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, UniqueConstraint, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db.session import Base

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index(
            "ux_signals_coin_id_timeframe_candle_timestamp_signal_type",
            "coin_id",
            "timeframe",
            "candle_timestamp",
            "signal_type",
            unique=True,
        ),
        Index("ix_signals_coin_id_timeframe_candle_timestamp", "coin_id", "timeframe", "candle_timestamp"),
        Index("ix_signals_coin_tf_ts", "coin_id", "timeframe", desc("candle_timestamp")),
        Index("ix_signals_pattern_timestamp", "signal_type", "candle_timestamp"),
        Index("ix_signals_coin_timestamp", "coin_id", "candle_timestamp"),
        Index("ix_signals_priority_score_desc", desc("priority_score")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False)
    priority_score: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    context_score: Mapped[float] = mapped_column(Float(53), nullable=False, default=1.0)
    regime_alignment: Mapped[float] = mapped_column(Float(53), nullable=False, default=1.0)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candle_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped[Coin] = relationship("Coin", back_populates="signals")


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

    coin: Mapped[Coin] = relationship("Coin", back_populates="signal_history")


class FinalSignal(Base):
    __tablename__ = "final_signals"
    __table_args__ = (
        Index("ix_final_signals_coin_tf_created_desc", "coin_id", "timeframe", desc("created_at")),
        Index("ix_final_signals_risk_adjusted_score_desc", desc("risk_adjusted_score")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    risk_adjusted_score: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped[Coin] = relationship("Coin", back_populates="final_signals")


class InvestmentDecision(Base):
    __tablename__ = "investment_decisions"
    __table_args__ = (
        Index("ix_investment_decisions_coin_tf_created_desc", "coin_id", "timeframe", desc("created_at")),
        Index("ix_investment_decisions_score_desc", desc("score")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    score: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped[Coin] = relationship("Coin", back_populates="investment_decisions")


class MarketDecision(Base):
    __tablename__ = "market_decisions"
    __table_args__ = (
        Index("ix_market_decisions_coin_tf_created_desc", "coin_id", "timeframe", desc("created_at")),
        Index("ix_market_decisions_confidence_desc", desc("confidence")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped[Coin] = relationship("Coin", back_populates="market_decisions")


class RiskMetric(Base):
    __tablename__ = "risk_metrics"

    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), primary_key=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    liquidity_score: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    slippage_risk: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    volatility_risk: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    coin: Mapped[Coin] = relationship("Coin", back_populates="risk_metrics")


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    rules: Mapped[list[StrategyRule]] = relationship(
        "StrategyRule",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyRule.pattern_slug",
    )
    performance: Mapped[StrategyPerformance | None] = relationship(
        "StrategyPerformance",
        back_populates="strategy",
        cascade="all, delete-orphan",
        uselist=False,
    )


class StrategyRule(Base):
    __tablename__ = "strategy_rules"

    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), primary_key=True)
    pattern_slug: Mapped[str] = mapped_column(String(96), primary_key=True)
    regime: Mapped[str] = mapped_column(String(32), nullable=False, default="*")
    sector: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    cycle: Mapped[str] = mapped_column(String(32), nullable=False, default="*")
    min_confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)

    strategy: Mapped[Strategy] = relationship("Strategy", back_populates="rules")


class StrategyPerformance(Base):
    __tablename__ = "strategy_performance"

    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), primary_key=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    avg_return: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    strategy: Mapped[Strategy] = relationship("Strategy", back_populates="performance")


__all__ = [
    "Signal",
    "SignalHistory",
    "FinalSignal",
    "InvestmentDecision",
    "MarketDecision",
    "RiskMetric",
    "Strategy",
    "StrategyRule",
    "StrategyPerformance",
]
