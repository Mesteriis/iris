from __future__ import annotations

from collections.abc import Mapping

from app.apps.anomalies.constants import DETECTOR_WEIGHTS, SEVERITY_BANDS
from app.apps.anomalies.schemas import DetectorFinding


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


class AnomalyScorer:
    def __init__(self, *, weights: Mapping[str, float] | None = None) -> None:
        self._weights = dict(weights or DETECTOR_WEIGHTS)

    def severity_for_score(self, score: float) -> str:
        for severity, lower_bound in SEVERITY_BANDS:
            if score >= lower_bound:
                return severity
        return "low"

    def score(self, finding: DetectorFinding) -> tuple[float, str, float]:
        active_components = {
            component_name: _clamp01(component_value)
            for component_name, component_value in finding.component_scores.items()
            if self._weights.get(component_name, 0.0) > 0.0 and component_value > 0.0
        }
        active_weight = sum(self._weights[component_name] for component_name in active_components)
        weighted_total = sum(
            self._weights[component_name] * component_value
            for component_name, component_value in active_components.items()
        )
        weighted_score = (weighted_total / active_weight) if active_weight > 0 else 0.0
        confidence = _clamp01((weighted_score * 0.60) + (_clamp01(finding.confidence) * 0.40))
        if not finding.isolated:
            confidence = _clamp01(confidence - 0.03)
        return weighted_score, self.severity_for_score(weighted_score), confidence
