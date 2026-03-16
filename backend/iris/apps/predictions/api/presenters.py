from typing import Any

from iris.apps.predictions.api.contracts import PredictionRead


def prediction_read(item: Any) -> PredictionRead:
    return PredictionRead.model_validate(item)


__all__ = ["prediction_read"]
