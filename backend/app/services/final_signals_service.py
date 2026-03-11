from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.final_signal import FinalSignal
from app.models.risk_metric import RiskMetric
from app.models.sector import Sector
from app.services.history_loader import get_coin_by_symbol


def _latest_final_signals_subquery():
    return (
        select(
            FinalSignal.id.label("id"),
            FinalSignal.coin_id.label("coin_id"),
            FinalSignal.timeframe.label("timeframe"),
            FinalSignal.decision.label("decision"),
            FinalSignal.confidence.label("confidence"),
            FinalSignal.risk_adjusted_score.label("risk_adjusted_score"),
            FinalSignal.reason.label("reason"),
            FinalSignal.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=(FinalSignal.coin_id, FinalSignal.timeframe),
                order_by=(FinalSignal.created_at.desc(), FinalSignal.id.desc()),
            )
            .label("final_signal_rank"),
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
            "risk_adjusted_score": float(row.risk_adjusted_score),
            "liquidity_score": float(row.liquidity_score or 0.0),
            "slippage_risk": float(row.slippage_risk or 0.0),
            "volatility_risk": float(row.volatility_risk or 0.0),
            "reason": str(row.reason),
            "created_at": row.created_at,
        }
        for row in rows
    ]


def list_final_signals(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    latest = _latest_final_signals_subquery()
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
            latest.c.risk_adjusted_score,
            RiskMetric.liquidity_score,
            RiskMetric.slippage_risk,
            RiskMetric.volatility_risk,
            latest.c.reason,
            latest.c.created_at,
        )
        .join(Coin, Coin.id == latest.c.coin_id)
        .outerjoin(Sector, Sector.id == Coin.sector_id)
        .outerjoin(
            RiskMetric,
            and_(
                RiskMetric.coin_id == latest.c.coin_id,
                RiskMetric.timeframe == latest.c.timeframe,
            ),
        )
        .where(latest.c.final_signal_rank == 1, Coin.deleted_at.is_(None))
        .order_by(latest.c.created_at.desc(), latest.c.id.desc())
        .limit(max(limit, 1))
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(latest.c.timeframe == timeframe)
    return _serialize_rows(db.execute(stmt).all())


def list_top_final_signals(db: Session, *, limit: int = 20) -> Sequence[dict[str, Any]]:
    latest = _latest_final_signals_subquery()
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
            latest.c.risk_adjusted_score,
            RiskMetric.liquidity_score,
            RiskMetric.slippage_risk,
            RiskMetric.volatility_risk,
            latest.c.reason,
            latest.c.created_at,
        )
        .join(Coin, Coin.id == latest.c.coin_id)
        .outerjoin(Sector, Sector.id == Coin.sector_id)
        .outerjoin(
            RiskMetric,
            and_(
                RiskMetric.coin_id == latest.c.coin_id,
                RiskMetric.timeframe == latest.c.timeframe,
            ),
        )
        .where(latest.c.final_signal_rank == 1, Coin.deleted_at.is_(None))
        .order_by(latest.c.risk_adjusted_score.desc(), latest.c.confidence.desc(), latest.c.created_at.desc())
        .limit(max(limit, 1))
    ).all()
    return _serialize_rows(rows)


def get_coin_final_signal(db: Session, symbol: str) -> dict[str, Any] | None:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        return None
    latest = _latest_final_signals_subquery()
    rows = db.execute(
        select(
            latest.c.timeframe,
            latest.c.decision,
            latest.c.confidence,
            latest.c.risk_adjusted_score,
            RiskMetric.liquidity_score,
            RiskMetric.slippage_risk,
            RiskMetric.volatility_risk,
            latest.c.reason,
            latest.c.created_at,
        )
        .outerjoin(
            RiskMetric,
            and_(
                RiskMetric.coin_id == latest.c.coin_id,
                RiskMetric.timeframe == latest.c.timeframe,
            ),
        )
        .where(latest.c.coin_id == coin.id, latest.c.final_signal_rank == 1)
        .order_by(latest.c.timeframe.asc())
    ).all()
    items = [
        {
            "timeframe": int(row.timeframe),
            "decision": str(row.decision),
            "confidence": float(row.confidence),
            "risk_adjusted_score": float(row.risk_adjusted_score),
            "liquidity_score": float(row.liquidity_score or 0.0),
            "slippage_risk": float(row.slippage_risk or 0.0),
            "volatility_risk": float(row.volatility_risk or 0.0),
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
