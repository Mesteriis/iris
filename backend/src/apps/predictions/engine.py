from __future__ import annotations

"""Legacy module kept as a shallow import alias for prediction services.

Active prediction persistence now lives in ``services.py`` and executes under the
shared async unit of work. This module intentionally contains no direct session
queries, raw SQL, or transaction ownership.
"""

from src.apps.predictions.services import PredictionService, PredictionSideEffectDispatcher

__all__ = ["PredictionService", "PredictionSideEffectDispatcher"]
