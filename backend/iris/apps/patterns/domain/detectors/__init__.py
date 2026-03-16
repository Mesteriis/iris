from iris.apps.patterns.domain.base import PatternDetector
from iris.apps.patterns.domain.detectors.continuation import build_continuation_detectors
from iris.apps.patterns.domain.detectors.momentum import build_momentum_detectors
from iris.apps.patterns.domain.detectors.structural import build_structural_detectors
from iris.apps.patterns.domain.detectors.volatility import build_volatility_detectors
from iris.apps.patterns.domain.detectors.volume import build_volume_detectors


def build_pattern_detectors() -> list[PatternDetector]:
    return [
        *build_structural_detectors(),
        *build_continuation_detectors(),
        *build_momentum_detectors(),
        *build_volatility_detectors(),
        *build_volume_detectors(),
    ]
