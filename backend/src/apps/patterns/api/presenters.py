from __future__ import annotations

from typing import Any

from src.apps.patterns.api.contracts import (
    CoinRegimeRead,
    DiscoveredPatternRead,
    PatternFeatureRead,
    PatternRead,
    SectorMetricsResponse,
    SectorRead,
    SignalRead,
)


def pattern_read(item: Any) -> PatternRead:
    return PatternRead.model_validate(item)


def pattern_feature_read(item: Any) -> PatternFeatureRead:
    return PatternFeatureRead.model_validate(item)


def discovered_pattern_read(item: Any) -> DiscoveredPatternRead:
    return DiscoveredPatternRead.model_validate(item)


def signal_read(item: Any) -> SignalRead:
    return SignalRead.model_validate(item)


def coin_regime_read(item: Any) -> CoinRegimeRead:
    return CoinRegimeRead.model_validate(item)


def sector_read(item: Any) -> SectorRead:
    return SectorRead.model_validate(item)


def sector_metrics_response(item: Any) -> SectorMetricsResponse:
    return SectorMetricsResponse.model_validate(item)


__all__ = [
    "coin_regime_read",
    "discovered_pattern_read",
    "pattern_feature_read",
    "pattern_read",
    "sector_metrics_response",
    "sector_read",
    "signal_read",
]
