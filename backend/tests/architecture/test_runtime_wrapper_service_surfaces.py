from tests.architecture.service_layer_baseline import (
    EXPECTED_RUNTIME_WRAPPER_SERVICE_SURFACE_VIOLATIONS,
)
from tests.architecture.service_layer_policy import (
    assert_policy_matches_baseline,
    collect_runtime_wrapper_service_surface_violations,
)


def test_runtime_wrapper_service_surfaces_match_baseline() -> None:
    assert_policy_matches_baseline(
        actual=collect_runtime_wrapper_service_surface_violations(),
        expected=EXPECTED_RUNTIME_WRAPPER_SERVICE_SURFACE_VIOLATIONS,
    )
