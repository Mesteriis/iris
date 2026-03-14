from __future__ import annotations

from tests.architecture.service_layer_baseline import EXPECTED_SERVICE_CONSTRUCTOR_DEPENDENCY_VIOLATIONS
from tests.architecture.service_layer_policy import (
    assert_policy_matches_baseline,
    collect_service_constructor_dependency_violations,
)


def test_service_constructor_dependency_policy() -> None:
    assert_policy_matches_baseline(
        actual=collect_service_constructor_dependency_violations(),
        expected=EXPECTED_SERVICE_CONSTRUCTOR_DEPENDENCY_VIOLATIONS,
    )
