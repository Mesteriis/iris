from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_PATTERN_FEATURES = [
    "pattern_detection",
    "pattern_clusters",
    "pattern_hierarchy",
    "market_regime_engine",
    "pattern_discovery_engine",
]


@dataclass(slots=True, frozen=True)
class PatternCatalogEntry:
    slug: str
    category: str
    cpu_cost: int


PATTERN_CATALOG: list[PatternCatalogEntry] = [
    PatternCatalogEntry("head_shoulders", "structural", 4),
    PatternCatalogEntry("inverse_head_shoulders", "structural", 4),
    PatternCatalogEntry("double_top", "structural", 2),
    PatternCatalogEntry("double_bottom", "structural", 2),
    PatternCatalogEntry("triple_top", "structural", 3),
    PatternCatalogEntry("triple_bottom", "structural", 3),
    PatternCatalogEntry("ascending_triangle", "structural", 3),
    PatternCatalogEntry("descending_triangle", "structural", 3),
    PatternCatalogEntry("symmetrical_triangle", "structural", 3),
    PatternCatalogEntry("rising_wedge", "structural", 3),
    PatternCatalogEntry("falling_wedge", "structural", 3),
    PatternCatalogEntry("bull_flag", "continuation", 2),
    PatternCatalogEntry("bear_flag", "continuation", 2),
    PatternCatalogEntry("pennant", "continuation", 2),
    PatternCatalogEntry("cup_and_handle", "continuation", 4),
    PatternCatalogEntry("breakout_retest", "continuation", 2),
    PatternCatalogEntry("consolidation_breakout", "continuation", 2),
    PatternCatalogEntry("rsi_divergence", "momentum", 2),
    PatternCatalogEntry("macd_cross", "momentum", 1),
    PatternCatalogEntry("macd_divergence", "momentum", 2),
    PatternCatalogEntry("momentum_exhaustion", "momentum", 2),
    PatternCatalogEntry("bollinger_squeeze", "volatility", 1),
    PatternCatalogEntry("bollinger_expansion", "volatility", 1),
    PatternCatalogEntry("atr_spike", "volatility", 1),
    PatternCatalogEntry("volume_spike", "volume", 1),
    PatternCatalogEntry("volume_climax", "volume", 2),
    PatternCatalogEntry("volume_divergence", "volume", 2),
]
