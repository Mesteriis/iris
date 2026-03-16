from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, SmallInteger, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db.session import Base
from src.core.i18n import CONTENT_KIND_GENERATED_TEXT

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


class AINotification(Base):
    __tablename__ = "ai_notifications"
    __table_args__ = (
        Index("ux_ai_notifications_source_event", "source_event_type", "source_event_id", unique=True),
        Index("ix_ai_notifications_created_desc", desc("created_at")),
        Index("ix_ai_notifications_coin_created_desc", "coin_id", desc("created_at")),
        Index("ix_ai_notifications_event_created_desc", "source_event_type", desc("created_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)
    content_kind: Mapped[str] = mapped_column(String(32), nullable=False, default=CONTENT_KIND_GENERATED_TEXT)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    refs_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_stream_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    causation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    coin: Mapped[Coin] = relationship("Coin")


__all__ = ["AINotification"]
