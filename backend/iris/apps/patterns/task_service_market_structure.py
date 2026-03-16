from iris.apps.patterns.runtime_results import PatternMarketStructureRefreshResult
from iris.apps.patterns.task_service_support import PatternTaskServiceSupport, payload_mapping
from iris.core.db.uow import BaseAsyncUnitOfWork


class PatternMarketStructureService(PatternTaskServiceSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternMarketStructureService")

    async def refresh(self) -> PatternMarketStructureRefreshResult:
        sectors = await self._refresh_sector_metrics()
        cycles = await self._refresh_market_cycles()
        context = await self._refresh_recent_signal_contexts(lookback_days=30)
        decisions = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signals = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        return PatternMarketStructureRefreshResult(
            status="ok",
            sectors=payload_mapping(sectors),
            cycles=payload_mapping(cycles),
            context=payload_mapping(context),
            decisions=payload_mapping(decisions),
            final_signals=payload_mapping(final_signals),
        )


__all__ = ["PatternMarketStructureService"]
