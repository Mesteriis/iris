from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, SmallInteger, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db.session import Base
from src.core.i18n import CONTENT_KIND_GENERATED_TEXT

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


class AIExplanation(Base):
    __tablename__ = "ai_explanations"
    __table_args__ = (
        Index("ux_ai_explanations_subject", "explain_kind", "subject_id", unique=True),
        Index("ix_ai_explanations_kind_updated_desc", "explain_kind", desc("updated_at")),
        Index("ix_ai_explanations_symbol_updated_desc", "symbol", desc("updated_at")),
        Index("ix_ai_explanations_coin_updated_desc", "coin_id", desc("updated_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    explain_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    coin_id: Mapped[int | None] = mapped_column(ForeignKey("coins.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timeframe: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    content_kind: Mapped[str] = mapped_column(String(32), nullable=False, default=CONTENT_KIND_GENERATED_TEXT)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    refs_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    subject_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    coin: Mapped[Coin | None] = relationship("Coin")


__all__ = ["AIExplanation"]
