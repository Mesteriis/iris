from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.market_data.services import get_coin_by_symbol_async
from src.apps.patterns.domain.regime import read_regime_details
from src.apps.patterns.selectors import _signal_select
from src.apps.signals.backtests import _BacktestPoint, _serialize_group, get_coin_backtests, list_backtests, list_top_backtests
from src.apps.signals.cache import read_cached_market_decision_async
from src.apps.signals.decision_selectors import (
    _latest_decisions_subquery,
    _serialize_rows as _serialize_decision_rows,
    get_coin_decision,
    list_decisions,
    list_top_decisions,
)
from src.apps.signals.final_signal_selectors import (
    _latest_final_signals_subquery,
    _serialize_rows as _serialize_final_signal_rows,
    get_coin_final_signal,
    list_final_signals,
    list_top_final_signals,
)
from src.apps.signals.fusion import evaluate_market_decision
from src.apps.signals.history import refresh_recent_signal_history, refresh_signal_history
from src.apps.signals.market_decision_selectors import (
    _latest_market_decisions_subquery,
    _serialize_rows as _serialize_market_decision_rows,
    get_coin_market_decision,
    list_market_decisions,
    list_top_market_decisions,
)
from src.apps.signals.models import FinalSignal, InvestmentDecision, MarketDecision, RiskMetric, Signal, SignalHistory, Strategy, StrategyPerformance
from src.apps.signals.strategies import list_strategies, list_strategy_performance

PREFERRED_TIMEFRAMES = (1440, 240, 60, 15)


async def _cluster_membership_map_async(
    db: AsyncSession,
    rows: Sequence[object],
) -> dict[tuple[int, int, object], list[str]]:
    if not rows:
        return {}
    coin_ids = sorted({int(row.coin_id) for row in rows})
    timeframes = sorted({int(row.timeframe) for row in rows})
    timestamps = sorted({row.candle_timestamp for row in rows})
    cluster_rows = (
        await db.execute(
            select(Signal.coin_id, Signal.timeframe, Signal.candle_timestamp, Signal.signal_type).where(
                Signal.coin_id.in_(coin_ids),
                Signal.timeframe.in_(timeframes),
                Signal.candle_timestamp.in_(timestamps),
                Signal.signal_type.like("pattern_cluster_%"),
            )
        )
    ).all()
    membership: dict[tuple[int, int, object], list[str]] = defaultdict(list)
    for row in cluster_rows:
        membership[(int(row.coin_id), int(row.timeframe), row.candle_timestamp)].append(str(row.signal_type))
    return membership


async def _serialize_signal_rows_async(
    db: AsyncSession,
    rows: Sequence[object],
) -> list[dict[str, object]]:
    membership = await _cluster_membership_map_async(db, rows)
    payload: list[dict[str, object]] = []
    for row in rows:
        regime_snapshot = read_regime_details(row.market_regime_details, int(row.timeframe))
        payload.append(
            {
                "id": int(row.id),
                "coin_id": int(row.coin_id),
                "symbol": str(row.symbol),
                "name": str(row.name),
                "sector": row.sector,
                "timeframe": int(row.timeframe),
                "signal_type": str(row.signal_type),
                "confidence": float(row.confidence),
                "priority_score": float(row.priority_score or 0.0),
                "context_score": float(row.context_score or 0.0),
                "regime_alignment": float(row.regime_alignment or 0.0),
                "candle_timestamp": row.candle_timestamp,
                "created_at": row.created_at,
                "market_regime": row.signal_market_regime
                or (regime_snapshot.regime if regime_snapshot is not None else row.market_regime),
                "cycle_phase": row.cycle_phase,
                "cycle_confidence": float(row.cycle_confidence) if row.cycle_confidence is not None else None,
                "cluster_membership": membership.get((int(row.coin_id), int(row.timeframe), row.candle_timestamp), []),
            }
        )
    return payload


async def list_enriched_signals_async(
    db: AsyncSession,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
):
    stmt = _signal_select().order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc()).limit(max(limit, 1))
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(Signal.timeframe == timeframe)
    rows = (await db.execute(stmt)).all()
    return await _serialize_signal_rows_async(db, rows)


async def list_top_signals_async(db: AsyncSession, *, limit: int = 20):
    rows = (
        await db.execute(
            _signal_select()
            .order_by(Signal.priority_score.desc(), Signal.candle_timestamp.desc(), Signal.created_at.desc())
            .limit(max(limit, 1))
        )
    ).all()
    return await _serialize_signal_rows_async(db, rows)


async def list_decisions_async(
    db: AsyncSession,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
):
    latest = _latest_decisions_subquery()
    stmt = (
        select(
            latest.c.id,
            latest.c.coin_id,
            Coin.symbol,
            Coin.name,
            Coin.sector_code.label("sector"),
            latest.c.timeframe,
            latest.c.decision,
            latest.c.confidence,
            latest.c.score,
            latest.c.reason,
            latest.c.created_at,
        )
        .join(Coin, Coin.id == latest.c.coin_id)
        .outerjoin(InvestmentDecision, InvestmentDecision.id == latest.c.id)
        .where(latest.c.decision_rank == 1, Coin.deleted_at.is_(None))
        .order_by(latest.c.created_at.desc(), latest.c.id.desc())
        .limit(max(limit, 1))
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(latest.c.timeframe == timeframe)
    return _serialize_decision_rows((await db.execute(stmt)).all())


async def list_top_decisions_async(db: AsyncSession, *, limit: int = 20):
    latest = _latest_decisions_subquery()
    rows = (
        await db.execute(
            select(
                latest.c.id,
                latest.c.coin_id,
                Coin.symbol,
                Coin.name,
                Coin.sector_code.label("sector"),
                latest.c.timeframe,
                latest.c.decision,
                latest.c.confidence,
                latest.c.score,
                latest.c.reason,
                latest.c.created_at,
            )
            .join(Coin, Coin.id == latest.c.coin_id)
            .outerjoin(InvestmentDecision, InvestmentDecision.id == latest.c.id)
            .where(latest.c.decision_rank == 1, Coin.deleted_at.is_(None))
            .order_by(latest.c.score.desc(), latest.c.confidence.desc(), latest.c.created_at.desc())
            .limit(max(limit, 1))
        )
    ).all()
    return _serialize_decision_rows(rows)


async def get_coin_decision_async(db: AsyncSession, symbol: str):
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        return None
    latest = _latest_decisions_subquery()
    rows = (
        await db.execute(
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
        )
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
    for current_timeframe in PREFERRED_TIMEFRAMES:
        if current_timeframe in items_by_timeframe:
            canonical = str(items_by_timeframe[current_timeframe]["decision"])
            break
    return {
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "canonical_decision": canonical,
        "items": items,
    }


async def list_market_decisions_async(
    db: AsyncSession,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
):
    latest = _latest_market_decisions_subquery()
    stmt = (
        select(
            latest.c.id,
            latest.c.coin_id,
            Coin.symbol,
            Coin.name,
            Coin.sector_code.label("sector"),
            latest.c.timeframe,
            latest.c.decision,
            latest.c.confidence,
            latest.c.signal_count,
            CoinMetrics.market_regime.label("regime"),
            latest.c.created_at,
        )
        .join(Coin, Coin.id == latest.c.coin_id)
        .outerjoin(CoinMetrics, CoinMetrics.coin_id == latest.c.coin_id)
        .where(latest.c.market_decision_rank == 1, Coin.deleted_at.is_(None))
        .order_by(latest.c.created_at.desc(), latest.c.id.desc())
        .limit(max(limit, 1))
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(latest.c.timeframe == timeframe)
    return _serialize_market_decision_rows((await db.execute(stmt)).all())


async def list_top_market_decisions_async(db: AsyncSession, *, limit: int = 20):
    latest = _latest_market_decisions_subquery()
    rows = (
        await db.execute(
            select(
                latest.c.id,
                latest.c.coin_id,
                Coin.symbol,
                Coin.name,
                Coin.sector_code.label("sector"),
                latest.c.timeframe,
                latest.c.decision,
                latest.c.confidence,
                latest.c.signal_count,
                CoinMetrics.market_regime.label("regime"),
                latest.c.created_at,
            )
            .join(Coin, Coin.id == latest.c.coin_id)
            .outerjoin(CoinMetrics, CoinMetrics.coin_id == latest.c.coin_id)
            .where(latest.c.market_decision_rank == 1, Coin.deleted_at.is_(None))
            .order_by(latest.c.confidence.desc(), latest.c.signal_count.desc(), latest.c.created_at.desc())
            .limit(max(limit, 1))
        )
    ).all()
    return _serialize_market_decision_rows(rows)


async def get_coin_market_decision_async(db: AsyncSession, symbol: str):
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        return None
    metrics = (
        await db.execute(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
    ).scalar_one_or_none()

    cached_items = []
    for timeframe in PREFERRED_TIMEFRAMES:
        cached = await read_cached_market_decision_async(coin_id=int(coin.id), timeframe=timeframe)
        if cached is None:
            continue
        detailed = read_regime_details(metrics.market_regime_details, timeframe) if metrics is not None else None
        cached_items.append(
            {
                "timeframe": timeframe,
                "decision": cached.decision,
                "confidence": cached.confidence,
                "signal_count": cached.signal_count,
                "regime": cached.regime
                or (detailed.regime if detailed is not None else (metrics.market_regime if metrics is not None else None)),
                "created_at": cached.created_at,
            }
        )
    if cached_items:
        items = sorted(cached_items, key=lambda item: item["timeframe"])
    else:
        latest = _latest_market_decisions_subquery()
        rows = (
            await db.execute(
                select(
                    latest.c.timeframe,
                    latest.c.decision,
                    latest.c.confidence,
                    latest.c.signal_count,
                    latest.c.created_at,
                    CoinMetrics.market_regime,
                    CoinMetrics.market_regime_details,
                )
                .outerjoin(CoinMetrics, CoinMetrics.coin_id == latest.c.coin_id)
                .where(latest.c.coin_id == coin.id, latest.c.market_decision_rank == 1)
                .order_by(latest.c.timeframe.asc())
            )
        ).all()
        items = []
        for row in rows:
            detailed = read_regime_details(row.market_regime_details, int(row.timeframe))
            items.append(
                {
                    "timeframe": int(row.timeframe),
                    "decision": str(row.decision),
                    "confidence": float(row.confidence),
                    "signal_count": int(row.signal_count),
                    "regime": detailed.regime if detailed is not None else row.market_regime,
                    "created_at": row.created_at,
                }
            )

    canonical = None
    items_by_timeframe = {item["timeframe"]: item for item in items}
    for current_timeframe in PREFERRED_TIMEFRAMES:
        if current_timeframe in items_by_timeframe:
            canonical = str(items_by_timeframe[current_timeframe]["decision"])
            break
    return {
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "canonical_decision": canonical,
        "items": items,
    }


async def list_final_signals_async(
    db: AsyncSession,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
):
    latest = _latest_final_signals_subquery()
    stmt = (
        select(
            latest.c.id,
            latest.c.coin_id,
            Coin.symbol,
            Coin.name,
            Coin.sector_code.label("sector"),
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
        .outerjoin(
            RiskMetric,
            and_(RiskMetric.coin_id == latest.c.coin_id, RiskMetric.timeframe == latest.c.timeframe),
        )
        .where(latest.c.final_signal_rank == 1, Coin.deleted_at.is_(None))
        .order_by(latest.c.created_at.desc(), latest.c.id.desc())
        .limit(max(limit, 1))
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(latest.c.timeframe == timeframe)
    return _serialize_final_signal_rows((await db.execute(stmt)).all())


async def list_top_final_signals_async(db: AsyncSession, *, limit: int = 20):
    latest = _latest_final_signals_subquery()
    rows = (
        await db.execute(
            select(
                latest.c.id,
                latest.c.coin_id,
                Coin.symbol,
                Coin.name,
                Coin.sector_code.label("sector"),
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
            .outerjoin(
                RiskMetric,
                and_(RiskMetric.coin_id == latest.c.coin_id, RiskMetric.timeframe == latest.c.timeframe),
            )
            .where(latest.c.final_signal_rank == 1, Coin.deleted_at.is_(None))
            .order_by(latest.c.risk_adjusted_score.desc(), latest.c.confidence.desc(), latest.c.created_at.desc())
            .limit(max(limit, 1))
        )
    ).all()
    return _serialize_final_signal_rows(rows)


async def get_coin_final_signal_async(db: AsyncSession, symbol: str):
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        return None
    latest = _latest_final_signals_subquery()
    rows = (
        await db.execute(
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
                and_(RiskMetric.coin_id == latest.c.coin_id, RiskMetric.timeframe == latest.c.timeframe),
            )
            .where(latest.c.coin_id == coin.id, latest.c.final_signal_rank == 1)
            .order_by(latest.c.timeframe.asc())
        )
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
    for current_timeframe in PREFERRED_TIMEFRAMES:
        if current_timeframe in items_by_timeframe:
            canonical = str(items_by_timeframe[current_timeframe]["decision"])
            break
    return {
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "canonical_decision": canonical,
        "items": items,
    }


async def list_backtests_async(
    db: AsyncSession,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    signal_type: str | None = None,
    lookback_days: int = 365,
    limit: int = 100,
):
    from src.apps.market_data.domain import utc_now

    cutoff = utc_now() - timedelta(days=lookback_days)
    stmt = (
        select(
            Coin.symbol,
            SignalHistory.signal_type,
            SignalHistory.timeframe,
            SignalHistory.confidence,
            SignalHistory.result_return,
            SignalHistory.result_drawdown,
            SignalHistory.evaluated_at,
        )
        .join(Coin, Coin.id == SignalHistory.coin_id)
        .where(
            Coin.deleted_at.is_(None),
            SignalHistory.candle_timestamp >= cutoff,
            SignalHistory.result_return.is_not(None),
            SignalHistory.result_drawdown.is_not(None),
        )
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(SignalHistory.timeframe == timeframe)
    if signal_type is not None:
        stmt = stmt.where(SignalHistory.signal_type == signal_type)
    rows = (await db.execute(stmt)).all()
    points = [
        _BacktestPoint(
            symbol=str(row.symbol),
            signal_type=str(row.signal_type),
            timeframe=int(row.timeframe),
            confidence=float(row.confidence),
            result_return=float(row.result_return),
            result_drawdown=float(row.result_drawdown),
            evaluated_at=row.evaluated_at,
        )
        for row in rows
    ]
    grouped: dict[tuple[str, int], list[_BacktestPoint]] = defaultdict(list)
    for point in points:
        grouped[(point.signal_type, point.timeframe)].append(point)
    payload = [
        _serialize_group(
            symbol=symbol.upper() if symbol is not None else None,
            signal_type=current_signal_type,
            timeframe=current_timeframe,
            points=current_points,
        )
        for (current_signal_type, current_timeframe), current_points in grouped.items()
    ]
    payload.sort(
        key=lambda row: (
            row["sample_size"],
            row["sharpe_ratio"],
            row["roi"],
            row["win_rate"],
        ),
        reverse=True,
    )
    return payload[: max(limit, 1)]


async def list_top_backtests_async(
    db: AsyncSession,
    *,
    timeframe: int | None = None,
    lookback_days: int = 365,
    limit: int = 20,
):
    rows = await list_backtests_async(
        db,
        timeframe=timeframe,
        lookback_days=lookback_days,
        limit=max(limit * 4, 50),
    )
    rows.sort(
        key=lambda row: (
            row["sharpe_ratio"],
            row["roi"],
            row["win_rate"],
            row["sample_size"],
        ),
        reverse=True,
    )
    return rows[: max(limit, 1)]


async def get_coin_backtests_async(
    db: AsyncSession,
    symbol: str,
    *,
    timeframe: int | None = None,
    signal_type: str | None = None,
    lookback_days: int = 365,
    limit: int = 50,
):
    coin = await get_coin_by_symbol_async(db, symbol)
    if coin is None:
        return None
    return {
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "items": list(
            await list_backtests_async(
                db,
                symbol=coin.symbol,
                timeframe=timeframe,
                signal_type=signal_type,
                lookback_days=lookback_days,
                limit=limit,
            )
        ),
    }


async def list_strategies_async(db: AsyncSession, *, enabled_only: bool = False, limit: int = 100):
    stmt = (
        select(Strategy)
        .options(selectinload(Strategy.rules), selectinload(Strategy.performance))
        .order_by(Strategy.enabled.desc(), Strategy.id.asc())
        .limit(max(limit, 1))
    )
    if enabled_only:
        stmt = stmt.where(Strategy.enabled.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    payload: list[dict[str, object]] = []
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


async def list_strategy_performance_async(db: AsyncSession, *, limit: int = 100):
    rows = (
        await db.execute(
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
        )
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


__all__ = [
    "evaluate_market_decision",
    "get_coin_backtests",
    "get_coin_backtests_async",
    "get_coin_decision",
    "get_coin_decision_async",
    "get_coin_final_signal",
    "get_coin_final_signal_async",
    "get_coin_market_decision",
    "get_coin_market_decision_async",
    "list_backtests",
    "list_backtests_async",
    "list_decisions",
    "list_decisions_async",
    "list_enriched_signals",
    "list_enriched_signals_async",
    "list_final_signals",
    "list_final_signals_async",
    "list_market_decisions",
    "list_market_decisions_async",
    "list_strategies",
    "list_strategies_async",
    "list_strategy_performance",
    "list_strategy_performance_async",
    "list_top_backtests",
    "list_top_backtests_async",
    "list_top_decisions",
    "list_top_decisions_async",
    "list_top_final_signals",
    "list_top_final_signals_async",
    "list_top_market_decisions",
    "list_top_market_decisions_async",
    "list_top_signals",
    "list_top_signals_async",
    "refresh_recent_signal_history",
    "refresh_signal_history",
]
