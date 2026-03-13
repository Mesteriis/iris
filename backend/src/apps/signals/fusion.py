from __future__ import annotations

"""Pure signal-fusion helpers kept for deterministic unit coverage only.

Active signal-fusion persistence lives in ``services.py`` and ``repositories.py``
 under the shared async unit of work. This module intentionally contains no
 direct session queries or transaction ownership.
"""

from src.apps.signals.fusion_support import (
    FUSION_CANDLE_GROUPS,
    FUSION_NEWS_TIMEFRAMES,
    FUSION_SIGNAL_LIMIT,
    MATERIAL_CONFIDENCE_DELTA,
    NEWS_FUSION_MAX_ITEMS,
    NEWS_FUSION_SCORE_CAP,
    FusionSnapshot,
    NewsImpactSnapshot,
    _apply_news_impact,
    _clamp,
    _decision_from_scores,
    _regime_weight,
    _signal_archetype,
    _signal_regime,
)

__all__ = [
    "FUSION_CANDLE_GROUPS",
    "FUSION_NEWS_TIMEFRAMES",
    "FUSION_SIGNAL_LIMIT",
    "MATERIAL_CONFIDENCE_DELTA",
    "NEWS_FUSION_MAX_ITEMS",
    "NEWS_FUSION_SCORE_CAP",
    "FusionSnapshot",
    "NewsImpactSnapshot",
    "_apply_news_impact",
    "_clamp",
    "_decision_from_scores",
    "_regime_weight",
    "_signal_archetype",
    "_signal_regime",
]
