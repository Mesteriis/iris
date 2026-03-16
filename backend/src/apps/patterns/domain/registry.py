from dataclasses import dataclass

from src.apps.patterns.domain.detectors import build_pattern_detectors


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
    # synchronized with live detectors so registry/statistics cover the full catalog
    *[
        PatternCatalogEntry(
            detector.slug,
            detector.category,
            {
                "head_shoulders": 4,
                "inverse_head_shoulders": 4,
                "cup_and_handle": 4,
                "high_tight_flag": 3,
            }.get(
                detector.slug,
                {
                    "structural": 3,
                    "continuation": 2,
                    "momentum": 2,
                    "volatility": 1,
                    "volume": 2,
                }.get(detector.category, 1),
            ),
        )
        for detector in build_pattern_detectors()
    ],
]


__all__ = ["PATTERN_CATALOG", "PatternCatalogEntry", "SUPPORTED_PATTERN_FEATURES"]
