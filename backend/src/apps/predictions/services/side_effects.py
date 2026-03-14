from __future__ import annotations

from src.apps.predictions.services.results import PredictionCreationBatch, PredictionEvaluationBatch
from src.core.db.persistence import PERSISTENCE_LOGGER


class PredictionSideEffectDispatcher:
    async def apply_creation(self, result: PredictionCreationBatch) -> None:
        from src.apps.predictions import services as services_module

        PERSISTENCE_LOGGER.debug(
            "prediction.side_effects.apply_creation",
            extra={
                "persistence": {
                    "event": "prediction.side_effects.apply_creation",
                    "component_type": "service",
                    "domain": "predictions",
                    "component": "PredictionSideEffectDispatcher",
                    "count": len(result.cache_snapshots),
                }
            },
        )
        for snapshot in result.cache_snapshots:
            await services_module.cache_prediction_snapshot_async(**snapshot.as_cache_kwargs())

    async def apply_evaluation(self, result: PredictionEvaluationBatch) -> None:
        from src.apps.predictions import services as services_module

        PERSISTENCE_LOGGER.debug(
            "prediction.side_effects.apply_evaluation",
            extra={
                "persistence": {
                    "event": "prediction.side_effects.apply_evaluation",
                    "component_type": "service",
                    "domain": "predictions",
                    "component": "PredictionSideEffectDispatcher",
                    "cache_snapshot_count": len(result.cache_snapshots),
                    "event_count": len(result.events),
                }
            },
        )
        for snapshot in result.cache_snapshots:
            await services_module.cache_prediction_snapshot_async(**snapshot.as_cache_kwargs())
        for event in result.events:
            services_module.publish_event(event.event_type, dict(event.payload))


__all__ = ["PredictionSideEffectDispatcher"]
