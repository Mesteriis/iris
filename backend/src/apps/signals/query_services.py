from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.market_data.repositories import CoinRepository
from src.apps.patterns.domain.regime import read_regime_details
from src.apps.patterns.query_builders import signal_select as _signal_select
from src.apps.signals.backtest_support import BacktestPoint, serialize_backtest_group
from src.apps.signals.cache import read_cached_market_decision_async
from src.apps.signals.models import (
    FinalSignal,
    InvestmentDecision,
    MarketDecision,
    RiskMetric,
    Signal,
    SignalHistory,
    Strategy,
    StrategyPerformance,
)
from src.apps.signals.query_builders import (
    latest_decisions_subquery as _latest_decisions_subquery,
)
from src.apps.signals.query_builders import (
    latest_final_signals_subquery as _latest_final_signals_subquery,
)
from src.apps.signals.query_builders import (
    latest_market_decisions_subquery as _latest_market_decisions_subquery,
)
from src.apps.signals.read_models import (
    BacktestSummaryReadModel,
    CoinBacktestsReadModel,
    CoinDecisionItemReadModel,
    CoinDecisionReadModel,
    CoinFinalSignalItemReadModel,
    CoinFinalSignalReadModel,
    CoinMarketDecisionItemReadModel,
    CoinMarketDecisionReadModel,
    FinalSignalReadModel,
    InvestmentDecisionReadModel,
    MarketDecisionReadModel,
    SignalReadModel,
    StrategyPerformanceReadModel,
    StrategyReadModel,
    StrategyRuleReadModel,
    backtest_summary_read_model_from_mapping,
    coin_decision_item_read_model_from_mapping,
    coin_final_signal_item_read_model_from_mapping,
    final_signal_read_model_from_mapping,
    investment_decision_read_model_from_mapping,
    market_decision_read_model_from_mapping,
    signal_read_model_from_mapping,
)
from src.core.db.persistence import AsyncQueryService

PREFERRED_TIMEFRAMES = (1440, 240, 60, 15)


def _canonical_decision(items: Sequence[object]) -> str | None:
    items_by_timeframe = {int(item.timeframe): str(item.decision) for item in items}
    for current_timeframe in PREFERRED_TIMEFRAMES:
        if current_timeframe in items_by_timeframe:
            return items_by_timeframe[current_timeframe]
    return None


async def _cluster_membership_map_async(
    session: AsyncSession,
    rows: Sequence[object],
) -> dict[tuple[int, int, object], list[str]]:
    if not rows:
        return {}
    coin_ids = sorted({int(row.coin_id) for row in rows})
    timeframes = sorted({int(row.timeframe) for row in rows})
    timestamps = sorted({row.candle_timestamp for row in rows})
    cluster_rows = (
        await session.execute(
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
    session: AsyncSession,
    rows: Sequence[object],
) -> tuple[SignalReadModel, ...]:
    membership = await _cluster_membership_map_async(session, rows)
    return tuple(
        signal_read_model_from_mapping(
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
                or (
                    regime_snapshot.regime
                    if (regime_snapshot := read_regime_details(row.market_regime_details, int(row.timeframe))) is not None
                    else row.market_regime
                ),
                "cycle_phase": row.cycle_phase,
                "cycle_confidence": float(row.cycle_confidence) if row.cycle_confidence is not None else None,
                "cluster_membership": membership.get((int(row.coin_id), int(row.timeframe), row.candle_timestamp), []),
            }
        )
        for row in rows
    )


class SignalQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="signals", service_name="SignalQueryService")
        self._coins = CoinRepository(session)

    async def list_signals(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> tuple[SignalReadModel, ...]:
        self._log_debug(
            "query.list_signals",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            loading_profile="cluster_projection",
        )
        stmt = _signal_select().order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc()).limit(max(limit, 1))
        if symbol is not None:
            stmt = stmt.where(Coin.symbol == symbol.upper())
        if timeframe is not None:
            stmt = stmt.where(Signal.timeframe == timeframe)
        rows = (await self.session.execute(stmt)).all()
        items = await _serialize_signal_rows_async(self.session, rows)
        self._log_debug("query.list_signals.result", mode="read", count=len(items))
        return items

    async def list_top_signals(self, *, limit: int = 20) -> tuple[SignalReadModel, ...]:
        self._log_debug(
            "query.list_top_signals",
            mode="read",
            limit=limit,
            loading_profile="cluster_projection",
        )
        rows = (
            await self.session.execute(
                _signal_select()
                .order_by(Signal.priority_score.desc(), Signal.candle_timestamp.desc(), Signal.created_at.desc())
                .limit(max(limit, 1))
            )
        ).all()
        items = await _serialize_signal_rows_async(self.session, rows)
        self._log_debug("query.list_top_signals.result", mode="read", count=len(items))
        return items

    async def get_signal_by_id(self, signal_id: int) -> SignalReadModel | None:
        self._log_debug("query.get_signal_by_id", mode="read", signal_id=signal_id, loading_profile="cluster_projection")
        rows = (
            await self.session.execute(
                _signal_select()
                .where(Signal.id == int(signal_id))
                .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc())
                .limit(1)
            )
        ).all()
        items = await _serialize_signal_rows_async(self.session, rows)
        if not items:
            self._log_debug("query.get_signal_by_id.result", mode="read", signal_id=signal_id, found=False)
            return None
        self._log_debug("query.get_signal_by_id.result", mode="read", signal_id=signal_id, found=True)
        return items[0]

    async def list_decisions(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> tuple[InvestmentDecisionReadModel, ...]:
        self._log_debug(
            "query.list_decisions",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            loading_profile="projection",
        )
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
        rows = (await self.session.execute(stmt)).all()
        items = tuple(investment_decision_read_model_from_mapping(row._mapping) for row in rows)
        self._log_debug("query.list_decisions.result", mode="read", count=len(items))
        return items

    async def list_top_decisions(self, *, limit: int = 20) -> tuple[InvestmentDecisionReadModel, ...]:
        self._log_debug("query.list_top_decisions", mode="read", limit=limit, loading_profile="projection")
        latest = _latest_decisions_subquery()
        rows = (
            await self.session.execute(
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
        items = tuple(investment_decision_read_model_from_mapping(row._mapping) for row in rows)
        self._log_debug("query.list_top_decisions.result", mode="read", count=len(items))
        return items

    async def get_decision_by_id(self, decision_id: int) -> InvestmentDecisionReadModel | None:
        self._log_debug("query.get_decision_by_id", mode="read", decision_id=decision_id, loading_profile="projection")
        row = await self.session.execute(
            select(
                InvestmentDecision.id,
                InvestmentDecision.coin_id,
                Coin.symbol,
                Coin.name,
                Coin.sector_code.label("sector"),
                InvestmentDecision.timeframe,
                InvestmentDecision.decision,
                InvestmentDecision.confidence,
                InvestmentDecision.score,
                InvestmentDecision.reason,
                InvestmentDecision.created_at,
            )
            .join(Coin, Coin.id == InvestmentDecision.coin_id)
            .where(InvestmentDecision.id == int(decision_id), Coin.deleted_at.is_(None))
            .limit(1)
        )
        result = row.first()
        if result is None:
            self._log_debug("query.get_decision_by_id.result", mode="read", decision_id=decision_id, found=False)
            return None
        item = investment_decision_read_model_from_mapping(result._mapping)
        self._log_debug("query.get_decision_by_id.result", mode="read", decision_id=decision_id, found=True)
        return item

    async def get_coin_decision(self, symbol: str) -> CoinDecisionReadModel | None:
        normalized_symbol = symbol.strip().upper()
        self._log_debug("query.get_coin_decision", mode="read", symbol=normalized_symbol)
        coin = await self._coins.get_by_symbol(normalized_symbol)
        if coin is None:
            self._log_debug("query.get_coin_decision.result", mode="read", symbol=normalized_symbol, found=False)
            return None
        latest = _latest_decisions_subquery()
        rows = (
            await self.session.execute(
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
        items = tuple(coin_decision_item_read_model_from_mapping(row._mapping) for row in rows)
        item = CoinDecisionReadModel(
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            canonical_decision=_canonical_decision(items),
            items=items,
        )
        self._log_debug("query.get_coin_decision.result", mode="read", symbol=normalized_symbol, found=True, count=len(items))
        return item

    async def list_market_decisions(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> tuple[MarketDecisionReadModel, ...]:
        self._log_debug(
            "query.list_market_decisions",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            loading_profile="projection",
        )
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
        rows = (await self.session.execute(stmt)).all()
        items = tuple(market_decision_read_model_from_mapping(row._mapping) for row in rows)
        self._log_debug("query.list_market_decisions.result", mode="read", count=len(items))
        return items

    async def list_top_market_decisions(self, *, limit: int = 20) -> tuple[MarketDecisionReadModel, ...]:
        self._log_debug("query.list_top_market_decisions", mode="read", limit=limit, loading_profile="projection")
        latest = _latest_market_decisions_subquery()
        rows = (
            await self.session.execute(
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
        items = tuple(market_decision_read_model_from_mapping(row._mapping) for row in rows)
        self._log_debug("query.list_top_market_decisions.result", mode="read", count=len(items))
        return items

    async def get_coin_market_decision(self, symbol: str) -> CoinMarketDecisionReadModel | None:
        normalized_symbol = symbol.strip().upper()
        self._log_debug("query.get_coin_market_decision", mode="read", symbol=normalized_symbol)
        coin = await self._coins.get_by_symbol(normalized_symbol)
        if coin is None:
            self._log_debug("query.get_coin_market_decision.result", mode="read", symbol=normalized_symbol, found=False)
            return None
        metrics = (
            await self.session.execute(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
        ).scalar_one_or_none()

        cached_items: list[CoinMarketDecisionItemReadModel] = []
        for timeframe in PREFERRED_TIMEFRAMES:
            cached = await read_cached_market_decision_async(coin_id=int(coin.id), timeframe=timeframe)
            if cached is None:
                continue
            detailed = read_regime_details(metrics.market_regime_details, timeframe) if metrics is not None else None
            cached_items.append(
                CoinMarketDecisionItemReadModel(
                    timeframe=timeframe,
                    decision=str(cached.decision),
                    confidence=float(cached.confidence),
                    signal_count=int(cached.signal_count),
                    regime=str(cached.regime)
                    if cached.regime is not None
                    else (
                        detailed.regime
                        if detailed is not None
                        else (str(metrics.market_regime) if metrics is not None and metrics.market_regime is not None else None)
                    ),
                    created_at=cached.created_at,
                )
            )
        if cached_items:
            self._log_debug(
                "query.get_coin_market_decision.cache_hit",
                mode="read",
                symbol=normalized_symbol,
                count=len(cached_items),
            )
            items = tuple(sorted(cached_items, key=lambda item: item.timeframe))
        else:
            self._log_debug(
                "query.get_coin_market_decision.cache_miss",
                mode="read",
                symbol=normalized_symbol,
                fallback="database",
            )
            latest = _latest_market_decisions_subquery()
            rows = (
                await self.session.execute(
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
            items = tuple(
                CoinMarketDecisionItemReadModel(
                    timeframe=int(row.timeframe),
                    decision=str(row.decision),
                    confidence=float(row.confidence),
                    signal_count=int(row.signal_count),
                    regime=(
                        detailed.regime
                        if (detailed := read_regime_details(row.market_regime_details, int(row.timeframe))) is not None
                        else (str(row.market_regime) if row.market_regime is not None else None)
                    ),
                    created_at=row.created_at,
                )
                for row in rows
            )
        item = CoinMarketDecisionReadModel(
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            canonical_decision=_canonical_decision(items),
            items=items,
        )
        self._log_debug(
            "query.get_coin_market_decision.result",
            mode="read",
            symbol=normalized_symbol,
            found=True,
            count=len(items),
        )
        return item

    async def list_final_signals(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> tuple[FinalSignalReadModel, ...]:
        self._log_debug(
            "query.list_final_signals",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            loading_profile="projection",
        )
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
        rows = (await self.session.execute(stmt)).all()
        items = tuple(final_signal_read_model_from_mapping(row._mapping) for row in rows)
        self._log_debug("query.list_final_signals.result", mode="read", count=len(items))
        return items

    async def list_top_final_signals(self, *, limit: int = 20) -> tuple[FinalSignalReadModel, ...]:
        self._log_debug("query.list_top_final_signals", mode="read", limit=limit, loading_profile="projection")
        latest = _latest_final_signals_subquery()
        rows = (
            await self.session.execute(
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
        items = tuple(final_signal_read_model_from_mapping(row._mapping) for row in rows)
        self._log_debug("query.list_top_final_signals.result", mode="read", count=len(items))
        return items

    async def get_coin_final_signal(self, symbol: str) -> CoinFinalSignalReadModel | None:
        normalized_symbol = symbol.strip().upper()
        self._log_debug("query.get_coin_final_signal", mode="read", symbol=normalized_symbol)
        coin = await self._coins.get_by_symbol(normalized_symbol)
        if coin is None:
            self._log_debug("query.get_coin_final_signal.result", mode="read", symbol=normalized_symbol, found=False)
            return None
        latest = _latest_final_signals_subquery()
        rows = (
            await self.session.execute(
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
        items = tuple(coin_final_signal_item_read_model_from_mapping(row._mapping) for row in rows)
        item = CoinFinalSignalReadModel(
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            canonical_decision=_canonical_decision(items),
            items=items,
        )
        self._log_debug(
            "query.get_coin_final_signal.result",
            mode="read",
            symbol=normalized_symbol,
            found=True,
            count=len(items),
        )
        return item

    async def list_backtests(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        signal_type: str | None = None,
        lookback_days: int = 365,
        limit: int = 100,
    ) -> tuple[BacktestSummaryReadModel, ...]:
        self._log_debug(
            "query.list_backtests",
            mode="read",
            symbol=symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            lookback_days=lookback_days,
            limit=limit,
            loading_profile="aggregated_projection",
        )
        items = await self._fetch_backtest_summaries(
            symbol=symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            lookback_days=lookback_days,
            limit=limit,
        )
        self._log_debug("query.list_backtests.result", mode="read", count=len(items))
        return items

    async def list_top_backtests(
        self,
        *,
        timeframe: int | None = None,
        lookback_days: int = 365,
        limit: int = 20,
    ) -> tuple[BacktestSummaryReadModel, ...]:
        self._log_debug(
            "query.list_top_backtests",
            mode="read",
            timeframe=timeframe,
            lookback_days=lookback_days,
            limit=limit,
            loading_profile="aggregated_projection",
        )
        rows = list(
            await self._fetch_backtest_summaries(
                timeframe=timeframe,
                lookback_days=lookback_days,
                limit=max(limit * 4, 50),
            )
        )
        rows.sort(
            key=lambda row: (
                row.sharpe_ratio,
                row.roi,
                row.win_rate,
                row.sample_size,
            ),
            reverse=True,
        )
        items = tuple(rows[: max(limit, 1)])
        self._log_debug("query.list_top_backtests.result", mode="read", count=len(items))
        return items

    async def get_coin_backtests(
        self,
        symbol: str,
        *,
        timeframe: int | None = None,
        signal_type: str | None = None,
        lookback_days: int = 365,
        limit: int = 50,
    ) -> CoinBacktestsReadModel | None:
        normalized_symbol = symbol.strip().upper()
        self._log_debug(
            "query.get_coin_backtests",
            mode="read",
            symbol=normalized_symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            lookback_days=lookback_days,
            limit=limit,
        )
        coin = await self._coins.get_by_symbol(normalized_symbol)
        if coin is None:
            self._log_debug("query.get_coin_backtests.result", mode="read", symbol=normalized_symbol, found=False)
            return None
        items = await self._fetch_backtest_summaries(
            symbol=str(coin.symbol),
            timeframe=timeframe,
            signal_type=signal_type,
            lookback_days=lookback_days,
            limit=limit,
        )
        item = CoinBacktestsReadModel(
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            items=items,
        )
        self._log_debug(
            "query.get_coin_backtests.result",
            mode="read",
            symbol=normalized_symbol,
            found=True,
            count=len(items),
        )
        return item

    async def list_strategies(
        self,
        *,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> tuple[StrategyReadModel, ...]:
        self._log_debug(
            "query.list_strategies",
            mode="read",
            enabled_only=enabled_only,
            limit=limit,
            loading_profile="with_rules_and_performance",
        )
        stmt = (
            select(Strategy)
            .options(selectinload(Strategy.rules), selectinload(Strategy.performance))
            .order_by(Strategy.enabled.desc(), Strategy.id.asc())
            .limit(max(limit, 1))
        )
        if enabled_only:
            stmt = stmt.where(Strategy.enabled.is_(True))
        rows = (await self.session.execute(stmt)).scalars().all()
        items = tuple(
            StrategyReadModel(
                id=int(row.id),
                name=str(row.name),
                description=str(row.description),
                enabled=bool(row.enabled),
                created_at=row.created_at,
                rules=tuple(
                    StrategyRuleReadModel(
                        pattern_slug=str(rule.pattern_slug),
                        regime=str(rule.regime),
                        sector=str(rule.sector),
                        cycle=str(rule.cycle),
                        min_confidence=float(rule.min_confidence),
                    )
                    for rule in row.rules
                ),
                performance=(
                    StrategyPerformanceReadModel(
                        strategy_id=int(row.performance.strategy_id),
                        name=str(row.name),
                        enabled=bool(row.enabled),
                        sample_size=int(row.performance.sample_size),
                        win_rate=float(row.performance.win_rate),
                        avg_return=float(row.performance.avg_return),
                        sharpe_ratio=float(row.performance.sharpe_ratio),
                        max_drawdown=float(row.performance.max_drawdown),
                        updated_at=row.performance.updated_at,
                    )
                    if row.performance is not None
                    else None
                ),
            )
            for row in rows
        )
        self._log_debug("query.list_strategies.result", mode="read", count=len(items))
        return items

    async def list_strategy_performance(self, *, limit: int = 100) -> tuple[StrategyPerformanceReadModel, ...]:
        self._log_debug("query.list_strategy_performance", mode="read", limit=limit, loading_profile="projection")
        rows = (
            await self.session.execute(
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
        items = tuple(
            StrategyPerformanceReadModel(
                strategy_id=int(row.strategy_id),
                name=str(row.name),
                enabled=bool(row.enabled),
                sample_size=int(row.sample_size),
                win_rate=float(row.win_rate),
                avg_return=float(row.avg_return),
                sharpe_ratio=float(row.sharpe_ratio),
                max_drawdown=float(row.max_drawdown),
                updated_at=row.updated_at,
            )
            for row in rows
        )
        self._log_debug("query.list_strategy_performance.result", mode="read", count=len(items))
        return items

    async def _fetch_backtest_summaries(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        signal_type: str | None = None,
        lookback_days: int = 365,
        limit: int = 100,
    ) -> tuple[BacktestSummaryReadModel, ...]:
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
        rows = (await self.session.execute(stmt)).all()
        points = [
            BacktestPoint(
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
        grouped: dict[tuple[str, int], list[BacktestPoint]] = defaultdict(list)
        for point in points:
            grouped[(point.signal_type, point.timeframe)].append(point)
        payload = [
            serialize_backtest_group(
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
        return tuple(backtest_summary_read_model_from_mapping(row) for row in payload[: max(limit, 1)])


__all__ = ["SignalQueryService"]
