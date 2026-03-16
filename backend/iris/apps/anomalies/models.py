from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Index, SmallInteger, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iris.core.db.session import Base

if TYPE_CHECKING:
    from iris.apps.market_data.models import Coin


class MarketAnomaly(Base):
    __tablename__ = "market_anomalies"
    __table_args__ = (
        Index(
            "ix_market_anomalies_coin_tf_type_detected_desc",
            "coin_id",
            "timeframe",
            "anomaly_type",
            desc("detected_at"),
        ),
        Index(
            "ix_market_anomalies_status_detected_desc",
            "status",
            desc("detected_at"),
        ),
        Index(
            "ix_market_anomalies_severity_score_desc",
            "severity",
            desc("score"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    score: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    coin: Mapped[Coin] = relationship("Coin")


class MarketStructureSnapshot(Base):
    __tablename__ = "market_structure_snapshots"
    __table_args__ = (
        Index(
            "ux_market_structure_snapshots_coin_tf_venue_ts",
            "coin_id",
            "timeframe",
            "venue",
            "timestamp",
            unique=True,
        ),
        Index(
            "ix_market_structure_snapshots_coin_tf_ts_desc",
            "coin_id",
            "timeframe",
            desc("timestamp"),
        ),
        Index(
            "ix_market_structure_snapshots_coin_venue_ts_desc",
            "coin_id",
            "venue",
            desc("timestamp"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    venue: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_price: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    mark_price: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    index_price: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    funding_rate: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    open_interest: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    basis: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    liquidations_long: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    liquidations_short: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    volume: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    coin: Mapped[Coin] = relationship("Coin")


__all__ = ["MarketAnomaly", "MarketStructureSnapshot"]
