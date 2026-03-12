from __future__ import annotations

from src.apps.patterns.task_service_base import PatternTaskBase
from src.apps.patterns.task_service_bootstrap import PatternBootstrapService
from src.apps.patterns.task_service_context import PatternContextMixin
from src.apps.patterns.task_service_decisions import PatternDecisionSignalsMixin
from src.apps.patterns.task_service_history import PatternHistoryStatisticsMixin
from src.apps.patterns.task_service_market import PatternMarketDiscoveryMixin
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
        await self._uow.commit()
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

    async def enrich(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: str | None = None,
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
        await self._uow.commit()
        return {"status": "ok", "context": context, "decision": decision, "final_signal": final_signal}


class PatternMarketStructureService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternMarketStructureService")

    async def refresh(self) -> dict[str, object]:
        sectors = await self._refresh_sector_metrics()
        cycles = await self._refresh_market_cycles()
        context = await self._refresh_recent_signal_contexts(lookback_days=30)
        decisions = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signals = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        await self._uow.commit()
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
        result = await self._refresh_discovered_patterns()
        await self._uow.commit()
        return result


class PatternStrategyService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternStrategyService")

    async def refresh(self) -> dict[str, object]:
        strategies = await self._refresh_strategies()
        decisions = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signals = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        await self._uow.commit()
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
    "PatternSignalContextService",
    "PatternStrategyService",
]
