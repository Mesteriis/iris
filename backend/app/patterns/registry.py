from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.pattern_feature import PatternFeature
from app.models.pattern_registry import PatternRegistry
from app.patterns.lifecycle import PatternLifecycleState, lifecycle_allows_detection
from app.patterns.detectors import build_pattern_detectors


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


def sync_pattern_metadata(db: Session) -> None:
    feature_stmt = insert(PatternFeature).values(
        [{"feature_slug": slug, "enabled": True} for slug in SUPPORTED_PATTERN_FEATURES]
    )
    db.execute(feature_stmt.on_conflict_do_nothing(index_elements=["feature_slug"]))

    registry_stmt = insert(PatternRegistry).values(
        [
            {
                "slug": item.slug,
                "category": item.category,
                "enabled": True,
                "cpu_cost": item.cpu_cost,
                "lifecycle_state": PatternLifecycleState.ACTIVE.value,
            }
            for item in PATTERN_CATALOG
        ]
    )
    db.execute(registry_stmt.on_conflict_do_nothing(index_elements=["slug"]))
    db.commit()


def feature_enabled(db: Session, feature_slug: str) -> bool:
    value = db.scalar(select(PatternFeature.enabled).where(PatternFeature.feature_slug == feature_slug))
    return bool(value) if value is not None else False


def active_detector_slugs(db: Session) -> set[str]:
    rows = db.execute(select(PatternRegistry.slug, PatternRegistry.enabled, PatternRegistry.lifecycle_state)).all()
    return {
        str(row.slug)
        for row in rows
        if lifecycle_allows_detection(str(row.lifecycle_state), bool(row.enabled))
    }


def load_active_detectors(db: Session, *, timeframe: int) -> list[object]:
    sync_pattern_metadata(db)
    enabled_slugs = active_detector_slugs(db)
    return [
        detector
        for detector in build_pattern_detectors()
        if detector.slug in enabled_slugs and timeframe in detector.supported_timeframes
    ]
