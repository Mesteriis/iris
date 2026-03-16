from sqlalchemy import select

from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.domain import utc_now
from src.apps.patterns.task_service_base import PatternTaskBase
from src.apps.patterns.task_service_bootstrap import PatternBootstrapService
from src.apps.patterns.task_service_context import PatternContextMixin
from src.apps.patterns.task_service_decisions import PatternDecisionSignalsMixin
from src.apps.patterns.task_service_history import PatternHistoryStatisticsMixin
from src.apps.patterns.task_service_market import PatternMarketDiscoveryMixin
from src.apps.patterns.task_service_runtime import PatternRealtimeService
from src.core.db.uow import BaseAsyncUnitOfWork


class _PatternTaskSupport(
    PatternHistoryStatisticsMixin,
    PatternContextMixin,
    PatternDecisionSignalsMixin,
    PatternMarketDiscoveryMixin,
    PatternTaskBase,
):
    pass


class PatternEvaluationService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternEvaluationService")

    async def run(self) -> dict[str, object]:
        history_result = await self._refresh_signal_history(lookback_days=365)
        statistics_result = await self._refresh_pattern_statistics()
        context_result = await self._refresh_recent_signal_contexts(lookback_days=30)
        decision_result = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signal_result = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        return {
            "status": "ok",
            "signal_history": history_result,
            "statistics": statistics_result,
            "context": context_result,
            "decisions": decision_result,
            "final_signals": final_signal_result,
        }


class PatternSignalContextService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternSignalContextService")

    async def enrich_context_only(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None = None,
    ) -> dict[str, object]:
        return await self._enrich_signal_context(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            candle_timestamp=candle_timestamp,
        )

    async def enrich(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None = None,
    ) -> dict[str, object]:
        context = await self._enrich_signal_context(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            candle_timestamp=candle_timestamp,
        )
        decision = await self._evaluate_investment_decision(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            emit_event=False,
        )
        final_signal = await self._evaluate_final_signal(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            emit_event=False,
        )
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(coin_id)).limit(1))
        return {
            "status": "ok",
            "context": context,
            "decision": decision,
            "final_signal": final_signal,
            "_feature_snapshot": {
                "coin_id": int(coin_id),
                "timeframe": int(timeframe),
                "timestamp": candle_timestamp if candle_timestamp is not None else utc_now(),
                "price_current": (
                    float(metrics.price_current)
                    if metrics is not None and metrics.price_current is not None
                    else None
                ),
                "rsi_14": float(metrics.rsi_14) if metrics is not None and metrics.rsi_14 is not None else None,
                "macd": float(metrics.macd) if metrics is not None and metrics.macd is not None else None,
            },
        }


class PatternMarketStructureService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternMarketStructureService")

    async def refresh(self) -> dict[str, object]:
        sectors = await self._refresh_sector_metrics()
        cycles = await self._refresh_market_cycles()
        context = await self._refresh_recent_signal_contexts(lookback_days=30)
        decisions = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signals = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        return {
            "status": "ok",
            "sectors": sectors,
            "cycles": cycles,
            "context": context,
            "decisions": decisions,
            "final_signals": final_signals,
        }


class PatternDiscoveryService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternDiscoveryService")

    async def refresh(self) -> dict[str, object]:
        return await self._refresh_discovered_patterns()


class PatternStrategyService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternStrategyService")

    async def refresh(self) -> dict[str, object]:
        strategies = await self._refresh_strategies()
        decisions = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signals = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        return {
            "status": "ok",
            "strategies": strategies,
            "decisions": decisions,
            "final_signals": final_signals,
        }


__all__ = [
    "PatternBootstrapService",
    "PatternDiscoveryService",
    "PatternEvaluationService",
    "PatternMarketStructureService",
    "PatternRealtimeService",
    "PatternSignalContextService",
    "PatternStrategyService",
]
