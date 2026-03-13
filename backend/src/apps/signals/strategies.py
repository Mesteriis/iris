from __future__ import annotations

import logging
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.apps.signals.models import Strategy
from src.apps.signals.models import StrategyPerformance
from src.apps.signals.read_models import (
    strategy_payload,
    strategy_performance_payload,
    strategy_performance_read_model_from_mapping,
    strategy_read_model_from_mapping,
)
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value


class SignalStrategyCompatibilityQuery:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        PERSISTENCE_LOGGER.log(
            level,
            event,
            extra={
                "persistence": {
                    "event": event,
                    "component_type": "compatibility_query",
                    "domain": "signals",
                    "component": "SignalStrategyCompatibilityQuery",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def list_strategies(self, *, enabled_only: bool = False, limit: int = 100) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_strategies.deprecated",
            mode="read",
            enabled_only=enabled_only,
            limit=limit,
        )
        self._log(
            logging.DEBUG,
            "compat.list_strategies.execute",
            mode="read",
            enabled_only=enabled_only,
            limit=limit,
        )
        stmt = (
            select(Strategy)
            .options(selectinload(Strategy.rules), selectinload(Strategy.performance))
            .order_by(Strategy.enabled.desc(), Strategy.id.asc())
            .limit(max(limit, 1))
        )
        if enabled_only:
            stmt = stmt.where(Strategy.enabled.is_(True))
        rows = self._db.scalars(stmt).all()
        items = [
            strategy_read_model_from_mapping(
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
                            "strategy_id": row.performance.strategy_id,
                            "name": row.name,
                            "enabled": row.enabled,
                            "sample_size": row.performance.sample_size,
                            "win_rate": row.performance.win_rate,
                            "avg_return": row.performance.avg_return,
                            "sharpe_ratio": row.performance.sharpe_ratio,
                            "max_drawdown": row.performance.max_drawdown,
                            "updated_at": row.performance.updated_at,
                        }
                        if row.performance is not None
                        else None
                    ),
                }
            )
            for row in rows
        ]
        result = [strategy_payload(item) for item in items]
        self._log(
            logging.INFO,
            "compat.list_strategies.result",
            mode="read",
            enabled_only=enabled_only,
            count=len(result),
        )
        return result

    def list_strategy_performance(self, *, limit: int = 100) -> Sequence[dict[str, Any]]:
        self._log(logging.WARNING, "compat.list_strategy_performance.deprecated", mode="read", limit=limit)
        self._log(logging.DEBUG, "compat.list_strategy_performance.execute", mode="read", limit=limit)
        rows = self._db.execute(
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
        result = [strategy_performance_payload(strategy_performance_read_model_from_mapping(row._mapping)) for row in rows]
        self._log(logging.INFO, "compat.list_strategy_performance.result", mode="read", count=len(result))
        return result


def list_strategies(db: Session, *, enabled_only: bool = False, limit: int = 100) -> Sequence[dict[str, Any]]:
    return SignalStrategyCompatibilityQuery(db).list_strategies(enabled_only=enabled_only, limit=limit)


def list_strategy_performance(db: Session, *, limit: int = 100) -> Sequence[dict[str, Any]]:
    return SignalStrategyCompatibilityQuery(db).list_strategy_performance(limit=limit)


__all__ = [
    "SignalStrategyCompatibilityQuery",
    "list_strategies",
    "list_strategy_performance",
]
