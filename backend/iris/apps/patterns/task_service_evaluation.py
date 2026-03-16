from iris.apps.patterns.runtime_results import PatternEvaluationRunResult
from iris.apps.patterns.task_service_support import PatternTaskServiceSupport, payload_mapping
from iris.core.db.uow import BaseAsyncUnitOfWork


class PatternEvaluationService(PatternTaskServiceSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternEvaluationService")

    async def run(self) -> PatternEvaluationRunResult:
        history_result = await self._refresh_signal_history(lookback_days=365)
        statistics_result = await self._refresh_pattern_statistics()
        context_result = await self._refresh_recent_signal_contexts(lookback_days=30)
        decision_result = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signal_result = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        return PatternEvaluationRunResult(
            status="ok",
            signal_history=payload_mapping(history_result),
            statistics=payload_mapping(statistics_result),
            context=payload_mapping(context_result),
            decisions=payload_mapping(decision_result),
            final_signals=payload_mapping(final_signal_result),
        )


__all__ = ["PatternEvaluationService"]
