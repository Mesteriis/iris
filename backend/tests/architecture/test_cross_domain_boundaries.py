from tests.architecture.service_layer_baseline import EXPECTED_CROSS_DOMAIN_BOUNDARY_VIOLATIONS
from tests.architecture.service_layer_policy import (
    assert_policy_matches_baseline,
    collect_cross_domain_boundary_violations,
)


def test_cross_domain_boundary_policy() -> None:
    assert_policy_matches_baseline(
        actual=collect_cross_domain_boundary_violations(),
        expected=EXPECTED_CROSS_DOMAIN_BOUNDARY_VIOLATIONS,
    )
