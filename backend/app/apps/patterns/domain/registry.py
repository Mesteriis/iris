from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.apps.patterns.models import PatternFeature
from app.apps.patterns.models import PatternRegistry
from app.apps.patterns.domain.lifecycle import PatternLifecycleState, lifecycle_allows_detection
from app.apps.patterns.domain.detectors import build_pattern_detectors


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
