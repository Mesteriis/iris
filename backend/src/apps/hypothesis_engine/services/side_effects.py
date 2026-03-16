from src.apps.hypothesis_engine.contracts import (
    HypothesisCreationResult,
    HypothesisEvaluationBatchResult,
    PromptMutationResult,
    WeightUpdateResult,
)
from src.apps.hypothesis_engine.memory.cache import invalidate_prompt_cache_async
from src.runtime.streams.publisher import publish_event


class PromptSideEffectDispatcher:
    async def apply_mutation(self, result: PromptMutationResult) -> None:
        for invalidation in result.cache_invalidations:
            await invalidate_prompt_cache_async(invalidation.name)


class HypothesisSideEffectDispatcher:
    async def apply_creation(self, result: HypothesisCreationResult) -> None:
        await self._apply_events(result.pending_events)

    async def apply_evaluation_batch(self, result: HypothesisEvaluationBatchResult) -> None:
        await self._apply_events(result.pending_events)

    async def apply_weight_update(self, result: WeightUpdateResult) -> None:
        await self._apply_events(result.pending_events)

    async def _apply_events(self, pending_events) -> None:
        for event in pending_events:
            publish_event(event.event_type, dict(event.payload))


__all__ = ["HypothesisSideEffectDispatcher", "PromptSideEffectDispatcher"]
