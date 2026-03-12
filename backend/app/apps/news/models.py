from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, JSON, String, Text, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.session import Base

if TYPE_CHECKING:
    from app.apps.news.models import NewsItem, NewsItemLink


class NewsSource(Base):
    __tablename__ = "news_sources"
    __table_args__ = (
        Index("ux_news_sources_plugin_display_name", "plugin_name", "display_name", unique=True),
        Index("ix_news_sources_enabled_updated_desc", "enabled", desc("updated_at")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plugin_name: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auth_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    credentials_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    cursor_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    items: Mapped[list["NewsItem"]] = relationship(
        "NewsItem",
        back_populates="source",
        cascade="all, delete-orphan",
        order_by="NewsItem.published_at",
    )


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        Index("ux_news_items_source_external", "source_id", "external_id", unique=True),
        Index("ix_news_items_published_desc", desc("published_at")),
        Index("ix_news_items_plugin_published_desc", "plugin_name", desc("published_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("news_sources.id", ondelete="CASCADE"), nullable=False)
    plugin_name: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    author_handle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    channel_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    symbol_hints: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    normalization_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    normalized_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float(53), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    source: Mapped["NewsSource"] = relationship("NewsSource", back_populates="items")
    links: Mapped[list["NewsItemLink"]] = relationship(
        "NewsItemLink",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="NewsItemLink.confidence",
    )


class NewsItemLink(Base):
    __tablename__ = "news_item_links"
    __table_args__ = (
        Index("ux_news_item_links_item_coin", "news_item_id", "coin_id", unique=True),
        Index("ix_news_item_links_coin_confidence_desc", "coin_id", desc("confidence")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    news_item_id: Mapped[int] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    coin_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    matched_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    link_type: Mapped[str] = mapped_column(String(24), nullable=False, default="symbol")
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    item: Mapped["NewsItem"] = relationship("NewsItem", back_populates="links")


__all__ = ["NewsItem", "NewsItemLink", "NewsSource"]
