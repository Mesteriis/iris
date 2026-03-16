from iris.apps.patterns.runtime_results import PatternStrategyRefreshResult
from iris.apps.patterns.task_service_support import PatternTaskServiceSupport, payload_mapping
from iris.core.db.uow import BaseAsyncUnitOfWork


class PatternStrategyService(PatternTaskServiceSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternStrategyService")

    async def refresh(self) -> PatternStrategyRefreshResult:
        strategies = await self._refresh_strategies()
        decisions = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signals = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        return PatternStrategyRefreshResult(
            status="ok",
            strategies=payload_mapping(strategies),
            decisions=payload_mapping(decisions),
            final_signals=payload_mapping(final_signals),
        )


__all__ = ["PatternStrategyService"]
