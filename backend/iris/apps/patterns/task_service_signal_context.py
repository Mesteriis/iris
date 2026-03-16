from iris.apps.market_data.domain import utc_now
from iris.apps.patterns.runtime_results import (
    PatternFeatureSnapshotResult,
    PatternSignalContextRefreshResult,
    PatternSignalContextRunResult,
)
from iris.apps.patterns.task_service_support import (
    PatternTaskServiceSupport,
    payload_int,
    payload_mapping,
    payload_optional_string,
    payload_string,
)
from iris.core.db.uow import BaseAsyncUnitOfWork


def _context_refresh_result(payload: object) -> PatternSignalContextRefreshResult:
    data = payload_mapping(payload)
    return PatternSignalContextRefreshResult(
        status=payload_string(data.get("status"), default="ok"),
        coin_id=payload_int(data.get("coin_id")),
        timeframe=payload_int(data.get("timeframe")),
        signals=payload_int(data.get("signals")),
        reason=payload_optional_string(data.get("reason")),
    )


class PatternSignalContextService(PatternTaskServiceSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternSignalContextService")

    async def enrich_context_only(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None = None,
    ) -> PatternSignalContextRefreshResult:
        payload = await self._enrich_signal_context(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            candle_timestamp=candle_timestamp,
        )
        return _context_refresh_result(payload)

    async def enrich(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None = None,
    ) -> PatternSignalContextRunResult:
        normalized_coin_id = int(coin_id)
        normalized_timeframe = int(timeframe)
        context = await self._enrich_signal_context(
            coin_id=normalized_coin_id,
            timeframe=normalized_timeframe,
            candle_timestamp=candle_timestamp,
        )
        decision = await self._evaluate_investment_decision(
            coin_id=normalized_coin_id,
            timeframe=normalized_timeframe,
            emit_event=False,
        )
        final_signal = await self._evaluate_final_signal(
            coin_id=normalized_coin_id,
            timeframe=normalized_timeframe,
            emit_event=False,
        )
        metrics = await self._queries.get_coin_metrics_snapshot(
            coin_id=normalized_coin_id,
            timeframe=normalized_timeframe,
        )
        return PatternSignalContextRunResult(
            status="ok",
            context=_context_refresh_result(context),
            decision=payload_mapping(decision),
            final_signal=payload_mapping(final_signal),
            feature_snapshot=PatternFeatureSnapshotResult(
                coin_id=normalized_coin_id,
                timeframe=normalized_timeframe,
                timestamp=candle_timestamp if candle_timestamp is not None else utc_now(),
                price_current=metrics.price_current if metrics is not None else None,
                rsi_14=metrics.rsi_14 if metrics is not None else None,
                macd=metrics.macd if metrics is not None else None,
            ),
        )


__all__ = ["PatternSignalContextService"]
