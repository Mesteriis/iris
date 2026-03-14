from __future__ import annotations

from tests.architecture.service_layer_baseline import EXPECTED_SERVICE_MODULE_THRESHOLD_VIOLATIONS
from tests.architecture.service_layer_policy import (
    assert_policy_matches_baseline,
    collect_service_module_threshold_violations,
)


def test_service_module_threshold_policy() -> None:
    assert_policy_matches_baseline(
        actual=collect_service_module_threshold_violations(),
        expected=EXPECTED_SERVICE_MODULE_THRESHOLD_VIOLATIONS,
    )

