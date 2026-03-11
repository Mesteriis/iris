from app.patterns.detectors.continuation import build_continuation_detectors
from app.patterns.detectors.momentum import build_momentum_detectors
from app.patterns.detectors.structural import build_structural_detectors
from app.patterns.detectors.volatility import build_volatility_detectors
from app.patterns.detectors.volume import build_volume_detectors


def build_pattern_detectors():
    return [
        *build_structural_detectors(),
        *build_continuation_detectors(),
        *build_momentum_detectors(),
        *build_volatility_detectors(),
        *build_volume_detectors(),
    ]
