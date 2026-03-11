from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.apps.signals.models import Strategy
from app.apps.signals.models import StrategyPerformance


def list_strategies(db: Session, *, enabled_only: bool = False, limit: int = 100) -> Sequence[dict[str, Any]]:
    stmt = (
        select(Strategy)
        .options(selectinload(Strategy.rules), selectinload(Strategy.performance))
        .order_by(Strategy.enabled.desc(), Strategy.id.asc())
        .limit(max(limit, 1))
    )
    if enabled_only:
        stmt = stmt.where(Strategy.enabled.is_(True))
    rows = db.scalars(stmt).all()
    payload: list[dict[str, Any]] = []
    for row in rows:
        performance = row.performance
        payload.append(
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "enabled": row.enabled,
                "created_at": row.created_at,
                "rules": [
                    {
                        "pattern_slug": rule.pattern_slug,
                        "regime": rule.regime,
                        "sector": rule.sector,
                        "cycle": rule.cycle,
                        "min_confidence": float(rule.min_confidence),
                    }
                    for rule in row.rules
                ],
                "performance": (
                    {
                        "strategy_id": performance.strategy_id,
                        "name": row.name,
                        "enabled": row.enabled,
                        "sample_size": performance.sample_size,
                        "win_rate": float(performance.win_rate),
                        "avg_return": float(performance.avg_return),
                        "sharpe_ratio": float(performance.sharpe_ratio),
                        "max_drawdown": float(performance.max_drawdown),
                        "updated_at": performance.updated_at,
                    }
                    if performance is not None
                    else None
                ),
            }
        )
    return payload


def list_strategy_performance(db: Session, *, limit: int = 100) -> Sequence[dict[str, Any]]:
    rows = db.execute(
        select(
            StrategyPerformance.strategy_id,
            Strategy.name,
            Strategy.enabled,
            StrategyPerformance.sample_size,
            StrategyPerformance.win_rate,
            StrategyPerformance.avg_return,
            StrategyPerformance.sharpe_ratio,
            StrategyPerformance.max_drawdown,
            StrategyPerformance.updated_at,
        )
        .join(Strategy, Strategy.id == StrategyPerformance.strategy_id)
        .order_by(
            Strategy.enabled.desc(),
            StrategyPerformance.sharpe_ratio.desc(),
            StrategyPerformance.win_rate.desc(),
            StrategyPerformance.avg_return.desc(),
        )
        .limit(max(limit, 1))
    ).all()
    return [
        {
            "strategy_id": int(row.strategy_id),
            "name": str(row.name),
            "enabled": bool(row.enabled),
            "sample_size": int(row.sample_size),
            "win_rate": float(row.win_rate),
            "avg_return": float(row.avg_return),
            "sharpe_ratio": float(row.sharpe_ratio),
            "max_drawdown": float(row.max_drawdown),
            "updated_at": row.updated_at,
        }
        for row in rows
    ]
