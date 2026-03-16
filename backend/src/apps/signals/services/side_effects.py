from src.apps.signals.cache import cache_market_decision_snapshot_async
from src.apps.signals.services.results import SignalFusionBatchResult, SignalFusionResult
from src.runtime.streams.publisher import publish_event


class SignalFusionSideEffectDispatcher:
    async def apply(self, result: SignalFusionResult | SignalFusionBatchResult) -> None:
        if isinstance(result, SignalFusionBatchResult):
            for item in result.items:
                await self.apply(item)
            return
        if result.cache_snapshot is not None:
            await cache_market_decision_snapshot_async(
                coin_id=result.cache_snapshot.coin_id,
                timeframe=result.cache_snapshot.timeframe,
                decision=result.cache_snapshot.decision,
                confidence=result.cache_snapshot.confidence,
                signal_count=result.cache_snapshot.signal_count,
                regime=result.cache_snapshot.regime,
                created_at=result.cache_snapshot.created_at,
            )
        for event in result.pending_events:
            publish_event(event.event_type, event.payload)


__all__ = ["SignalFusionSideEffectDispatcher"]
