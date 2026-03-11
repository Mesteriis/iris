from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.investment_decision import InvestmentDecision
from app.models.sector import Sector
from app.services.history_loader import get_coin_by_symbol


def _latest_decisions_subquery():
    return (
        select(
            InvestmentDecision.id.label("id"),
            InvestmentDecision.coin_id.label("coin_id"),
            InvestmentDecision.timeframe.label("timeframe"),
            InvestmentDecision.decision.label("decision"),
            InvestmentDecision.confidence.label("confidence"),
            InvestmentDecision.score.label("score"),
            InvestmentDecision.reason.label("reason"),
            InvestmentDecision.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=(InvestmentDecision.coin_id, InvestmentDecision.timeframe),
                order_by=(InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc()),
            )
            .label("decision_rank"),
        )
        .subquery()
    )


def _serialize_rows(rows: Sequence[object]) -> list[dict[str, Any]]:
    return [
        {
            "id": int(row.id),
            "coin_id": int(row.coin_id),
            "symbol": str(row.symbol),
            "name": str(row.name),
            "sector": row.sector,
            "timeframe": int(row.timeframe),
            "decision": str(row.decision),
            "confidence": float(row.confidence),
            "score": float(row.score),
            "reason": str(row.reason),
            "created_at": row.created_at,
        }
        for row in rows
    ]


def list_decisions(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    latest = _latest_decisions_subquery()
    stmt = (
        select(
            latest.c.id,
            latest.c.coin_id,
            Coin.symbol,
            Coin.name,
            Sector.name.label("sector"),
            latest.c.timeframe,
            latest.c.decision,
            latest.c.confidence,
            latest.c.score,
            latest.c.reason,
            latest.c.created_at,
        )
        .join(Coin, Coin.id == latest.c.coin_id)
        .outerjoin(Sector, Sector.id == Coin.sector_id)
        .where(latest.c.decision_rank == 1, Coin.deleted_at.is_(None))
        .order_by(latest.c.created_at.desc(), latest.c.id.desc())
        .limit(max(limit, 1))
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(latest.c.timeframe == timeframe)
    return _serialize_rows(db.execute(stmt).all())


def list_top_decisions(db: Session, *, limit: int = 20) -> Sequence[dict[str, Any]]:
    latest = _latest_decisions_subquery()
    rows = db.execute(
        select(
            latest.c.id,
            latest.c.coin_id,
            Coin.symbol,
            Coin.name,
            Sector.name.label("sector"),
            latest.c.timeframe,
            latest.c.decision,
            latest.c.confidence,
            latest.c.score,
            latest.c.reason,
            latest.c.created_at,
        )
        .join(Coin, Coin.id == latest.c.coin_id)
        .outerjoin(Sector, Sector.id == Coin.sector_id)
        .where(latest.c.decision_rank == 1, Coin.deleted_at.is_(None))
        .order_by(latest.c.score.desc(), latest.c.confidence.desc(), latest.c.created_at.desc())
        .limit(max(limit, 1))
    ).all()
    return _serialize_rows(rows)


def get_coin_decision(db: Session, symbol: str) -> dict[str, Any] | None:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        return None
    latest = _latest_decisions_subquery()
    rows = db.execute(
        select(
            latest.c.timeframe,
            latest.c.decision,
            latest.c.confidence,
            latest.c.score,
            latest.c.reason,
            latest.c.created_at,
        )
        .where(latest.c.coin_id == coin.id, latest.c.decision_rank == 1)
        .order_by(latest.c.timeframe.asc())
    ).all()
    items = [
        {
            "timeframe": int(row.timeframe),
            "decision": str(row.decision),
            "confidence": float(row.confidence),
            "score": float(row.score),
            "reason": str(row.reason),
            "created_at": row.created_at,
        }
        for row in rows
    ]
    canonical = None
    items_by_timeframe = {item["timeframe"]: item for item in items}
    for current_timeframe in (1440, 240, 60, 15):
        if current_timeframe in items_by_timeframe:
            canonical = str(items_by_timeframe[current_timeframe]["decision"])
            break
    return {
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "canonical_decision": canonical,
        "items": items,
    }
