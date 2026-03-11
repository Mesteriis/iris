from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.candle import Candle
    from app.models.coin_metrics import CoinMetrics
    from app.models.indicator_cache import IndicatorCache
    from app.models.signal import Signal


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
    signals: Mapped[list["Signal"]] = relationship(
        back_populates="coin",
        cascade="all, delete-orphan",
        order_by="Signal.candle_timestamp",
    )
