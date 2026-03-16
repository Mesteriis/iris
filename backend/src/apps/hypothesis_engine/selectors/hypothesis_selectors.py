from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.apps.hypothesis_engine.constants import HYPOTHESIS_STATUS_ACTIVE
from src.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval, AIPrompt


def prompt_versions_stmt(*, name: str | None = None):
    stmt = select(AIPrompt).order_by(AIPrompt.name.asc(), AIPrompt.version.desc(), AIPrompt.id.desc())
    if name is not None:
        stmt = stmt.where(AIPrompt.name == name)
    return stmt


def active_prompt_stmt(name: str):
    return (
        select(AIPrompt)
        .where(AIPrompt.name == name, AIPrompt.is_active.is_(True))
        .order_by(AIPrompt.version.desc(), AIPrompt.id.desc())
        .limit(1)
    )


def hypotheses_stmt(*, limit: int, status: str | None = None, coin_id: int | None = None):
    stmt = select(AIHypothesis).order_by(AIHypothesis.created_at.desc(), AIHypothesis.id.desc()).limit(max(limit, 1))
    if status is not None:
        stmt = stmt.where(AIHypothesis.status == status)
    if coin_id is not None:
        stmt = stmt.where(AIHypothesis.coin_id == coin_id)
    return stmt


def due_hypotheses_stmt(now: datetime, *, limit: int):
    return (
        select(AIHypothesis)
        .options(selectinload(AIHypothesis.evals))
        .where(AIHypothesis.status == HYPOTHESIS_STATUS_ACTIVE, AIHypothesis.eval_due_at <= now)
        .order_by(AIHypothesis.eval_due_at.asc(), AIHypothesis.id.asc())
        .limit(max(limit, 1))
    )


def hypothesis_evals_stmt(*, limit: int, hypothesis_id: int | None = None):
    stmt = (
        select(AIHypothesisEval)
        .options(selectinload(AIHypothesisEval.hypothesis))
        .order_by(AIHypothesisEval.evaluated_at.desc(), AIHypothesisEval.id.desc())
        .limit(max(limit, 1))
    )
    if hypothesis_id is not None:
        stmt = stmt.where(AIHypothesisEval.hypothesis_id == hypothesis_id)
    return stmt
