from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    desc,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iris.core.db.session import Base

if TYPE_CHECKING:
    from iris.apps.market_data.models import Coin


class AIPrompt(Base):
    __tablename__ = "ai_prompts"
    __table_args__ = (
        Index("ux_ai_prompts_name_version", "name", "version", unique=True),
        Index("ix_ai_prompts_task_active_updated_desc", "task", "is_active", desc("updated_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    veil_lifted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    template: Mapped[str] = mapped_column(Text, nullable=False)
    vars_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AIHypothesis(Base):
    __tablename__ = "ai_hypotheses"
    __table_args__ = (
        Index("ix_ai_hypotheses_status_eval_due_at", "status", "eval_due_at"),
        Index("ix_ai_hypotheses_coin_tf_created_desc", "coin_id", "timeframe", desc("created_at")),
        Index("ix_ai_hypotheses_type_confidence_desc", "type", desc("confidence")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    hypothesis_type: Mapped[str] = mapped_column("type", String(64), nullable=False)
    statement_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    horizon_min: Mapped[int] = mapped_column(Integer, nullable=False, default=240)
    eval_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_stream_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    coin: Mapped[Coin] = relationship("Coin")
    evals: Mapped[list[AIHypothesisEval]] = relationship(
        "AIHypothesisEval",
        back_populates="hypothesis",
        cascade="all, delete-orphan",
        order_by="AIHypothesisEval.evaluated_at",
    )


class AIHypothesisEval(Base):
    __tablename__ = "ai_hypothesis_evals"
    __table_args__ = (
        Index("ux_ai_hypothesis_evals_hypothesis_id", "hypothesis_id", unique=True),
        Index("ix_ai_hypothesis_evals_evaluated_desc", desc("evaluated_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hypothesis_id: Mapped[int] = mapped_column(ForeignKey("ai_hypotheses.id", ondelete="CASCADE"), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    score: Mapped[float] = mapped_column(Float(53), nullable=False, default=0.0)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    hypothesis: Mapped[AIHypothesis] = relationship("AIHypothesis", back_populates="evals")


class AIWeight(Base):
    __tablename__ = "ai_weights"
    __table_args__ = (
        Index("ux_ai_weights_scope_key", "scope", "key", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    weight_key: Mapped[str] = mapped_column("key", String(120), nullable=False)
    alpha: Mapped[float] = mapped_column(Float(53), nullable=False, default=1.0, server_default="1")
    beta: Mapped[float] = mapped_column(Float(53), nullable=False, default=1.0, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = ["AIHypothesis", "AIHypothesisEval", "AIPrompt", "AIWeight"]
